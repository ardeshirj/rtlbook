"""ParisaOCR's line recognizer (a Kraken model, PyTorch) as an ONNX file, for rtlbook's image (readers.ParisaOCR).
Run by docker/Dockerfile's parisaocr stage: python parisaocr_onnx.py OUT_DIR; writes parisaocr.onnx and codec.json.

The model was trained with every line padded on the right to 2560 columns (kraken#810), and its squeeze-and-
excitation blocks average each channel over that whole width, so it reads well only when padded so. Computing those
columns costs most of the time: lines are 1000-1500 wide at its 96-pixel height. Deep in the padding every column is
alike, so the padded run is the same as a short one (the line and a margin of white) with that column counted as
often as the padding is long. Here each SE average adds the missing columns back that way (DESIGN.md §4.5). Two more
patches: the backbone's last pooling and Kraken's output lengths use the tensors' sizes, which the export would
otherwise freeze at the sample's width. The file is then checked against the unchanged model, padded to 2560.
"""
import json
import sys
import types
from pathlib import Path

import torch
import torch.nn.functional as F

FULL, SCALE, MARGIN = 2560, 4, 128  # padded width; SE blocks run at 1/4 of the input width; the margin rtlbook adds


def load():
    from kraken.tasks import RecognitionTaskModel
    from parisaocr.cli import BUNDLED_MODEL

    return RecognitionTaskModel.load_model(str(BUNDLED_MODEL)).net


def patched(nn_):
    def backbone_forward(self, x):
        for b in (self.conv1, self.blocks2, self.blocks3, self.blocks4, self.blocks5, self.blocks6):
            x = b(x)
        return F.avg_pool2d(x, kernel_size=(int(x.shape[2]), 2))  # the height is always 96 in: a constant

    def network_forward(self, x, seq_lens):
        feat = self.backbone(x)
        w_in, w_out = torch._shape_as_tensor(x)[3], torch._shape_as_tensor(feat)[3]
        out_lens = torch.minimum((seq_lens * w_out // w_in).clamp(min=1), w_out)
        mask = torch.arange(w_out)[None, :] < out_lens[:, None]
        logits = self.head(self.neck(feat, mask))
        return logits.permute(0, 2, 1).unsqueeze(2), out_lens

    def se_forward(self, x):
        w_in, n = nn_._ctx
        w = torch._shape_as_tensor(x)[3]
        full = torch.clamp(w_in, min=FULL) // SCALE
        mid = torch.minimum((n + w_in) // (2 * SCALE), w - 1)  # a column in the middle of the margin
        col = torch.index_select(x, 3, mid).sum(dim=(2, 3), keepdim=True)
        mean = (x.sum(dim=(2, 3), keepdim=True) + (full - w).float() * col) / (full.float() * x.shape[2])
        return x * self.hardsigmoid(self.conv2(self.relu(self.conv1(mean))))

    nn_.backbone.forward = types.MethodType(backbone_forward, nn_.backbone)
    nn_.forward = types.MethodType(network_forward, nn_)
    for m in nn_.modules():
        if type(m).__name__ == "SELayer":
            m.forward = types.MethodType(se_forward, m)

    class Wrapped(torch.nn.Module):
        """image (N, 3, 96, W): the line 0..1 inverted, margin included; lens (N,): the line's own width ->
        probabilities (N, classes, W/8), class 0 the CTC blank, and the output lengths (N,)"""

        def __init__(self):
            super().__init__()
            self.inner = nn_

        def forward(self, x, lens):
            nn_._ctx = (torch._shape_as_tensor(x)[3], lens)
            logits, olens = self.inner(x, lens)
            return logits.softmax(1).squeeze(2), olens

    return Wrapped().eval()


def main(out: Path):
    import numpy as np
    import onnxruntime as ort

    out.mkdir(parents=True, exist_ok=True)
    net = load()
    torch.manual_seed(0)
    x = torch.zeros(1, 3, 96, 1024)
    x[..., 40:880] = (torch.rand(1, 1, 96, 840) > 0.8).float()  # specks for a line: the check needs no book
    torch.onnx.export(patched(net.nn.eval()), (x, torch.tensor([896])), out / "parisaocr.onnx",
                      input_names=["image", "lens"], output_names=["probs", "olens"], opset_version=17, dynamo=False,
                      dynamic_axes={"image": {0: "n", 3: "w"}, "lens": {0: "n"}, "probs": {0: "n", 2: "wo"},
                                    "olens": {0: "n"}})
    codec = {int(v[0]): k for k, v in net.codec.c2l.items()}
    (out / "codec.json").write_text(json.dumps(codec, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    ref = load().nn.eval()  # unchanged, padded to 2560 as trained
    s = ort.InferenceSession(str(out / "parisaocr.onnx"), providers=["CPUExecutionProvider"])
    for n in (500, 1200, 2300):
        w = min(FULL, -(-(n + MARGIN) // 32) * 32)
        line = torch.zeros(1, 3, 96, FULL)
        line[..., 16:n - 16] = (torch.rand(1, 1, 96, n - 32) > 0.8).float()
        with torch.no_grad():
            logits, olens = ref(line, torch.tensor([n]))
        want = logits.softmax(1).squeeze(2).numpy()[..., :int(olens[0])]
        got, golens = s.run(None, {"image": line[..., :w].numpy(), "lens": np.array([n], np.int64)})
        diff = float(abs(got[..., :int(golens[0])] - want).max())
        assert int(golens[0]) == int(olens[0]) and diff < 1e-3, (n, diff)
        print(f"line {n} wide: the same as padded to {FULL} (largest difference {diff:.6f})")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
