"""Line readers: one printed line's image in, its text and confidence out (ROADMAP.md "Reader slot and scorecard").

`convert` reads a scan's lines through this slot (`pipeline.read_lines`: Tesseract finds the lines, each is cut and
read alone) and an exported PDF's whole pages in Tesseract's one call (`ocr.ocr_lines`); the scorecard (`rtlbook
bench`) scores each reader on checked lines. Tesseract is in rtlbook's image; the others are open models measured for
the scorecard, in a separate image (`docker/Dockerfile.readers`).
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Protocol

from PIL import Image

from rtlbook import ocr, preprocess


def _torch():
    """PyTorch, on as many threads as the image allows: rtlbook's sets OMP_THREAD_LIMIT=1 (pages run side by side),
    which PyTorch doesn't follow; its own 8 threads then wait on each other and a line never finishes."""
    import torch  # the readers image only

    if limit := os.environ.get("OMP_THREAD_LIMIT"):
        torch.set_num_threads(int(limit))
    return torch


class Reader(Protocol):
    name: str

    def read(self, image: Image.Image) -> tuple[str, float | None]:
        """The line's text, words in reading order, and a confidence (0–100, the reader's own scale) or None."""
        ...


class Tesseract:
    """Tesseract on one line as a raw line (`--psm 13`), the image binarized as `convert` does with whole pages. On the
    1932 book's checked test lines: 6.4% letters wrong, against 19.8% with `--psm 7` (one line, but with Tesseract's
    own line handling, which the crop's bits of the neighbouring lines confuse) and 9.6% reading whole pages."""

    def __init__(self, lang: str = "fas"):
        self.lang = lang
        self.name = f"{ocr.tesseract_version()} {lang}"  # e.g. "tesseract 5.3.0 fas": another version is another reader

    def read(self, image: Image.Image) -> tuple[str, float | None]:
        return ocr.read_line(preprocess.prepare(image), self.lang)  # through the C API: no program start a line


class Kraken:
    """A Kraken recognition model on one line, through ParisaOCR's reader (it handles PP-OCR models and the
    right-to-left order). Needs the readers image (`make readers`): PyTorch, Kraken and ParisaOCR aren't in rtlbook's."""

    def __init__(self, model: str | Path, name: str):
        from parisaocr.kraken_reader import KrakenReader  # the readers image only

        _torch()
        self.name = name
        self._reader = KrakenReader(model, "cpu")

    def read(self, image: Image.Image) -> tuple[str, float | None]:
        from parisaocr.reader import line_text

        buf = io.BytesIO()
        image.save(buf, "PNG")
        words = [w for line in self._reader.read(buf, self._reader.SINGLE_LINE) for w in line]
        if not words:
            return "", None
        return line_text(words), round(sum(w.conf for w in words) / len(words), 1)


def parisaocr() -> Kraken:
    """ParisaOCR's model (Apache-2.0): PaddleOCR's PP-OCRv6 recognizer design, trained for Persian print."""
    from parisaocr.cli import BUNDLED_MODEL

    return Kraken(BUNDLED_MODEL, f"parisaocr {BUNDLED_MODEL.stem.removeprefix('parisaocr-')}")


class Hezar:
    """Hezar's printed Persian CRNN (Apache-2.0), from Hugging Face."""

    def __init__(self, model: str = "hezarai/crnn-fa-printed-96-long"):
        from hezar.models import Model  # the readers image only

        _torch()
        self.name = f"hezar {model.split('/')[-1]}"
        self._model = Model.load(model)

    def read(self, image: Image.Image) -> tuple[str, float | None]:
        return self._model.predict(image.convert("RGB"))[0].text, None


class WeightedAI:
    """WeightedAI's Persian_OCR (Apache-2.0): a CNN + Transformer trained with CTC on ~600,000 made-up lines (Wikipedia
    text rendered in 49 fonts). Its model definition comes with its weights (`model.py`)."""

    HEIGHT, WIDTH = 64, 1600  # its input: the line scaled to 64 pixels high, on a white strip 1600 wide

    def __init__(self):
        import importlib.util
        import json

        torch = _torch()
        folder = Path(os.environ.get("RTLBOOK_MODELS", "/opt/models")) / "weightedai-persian-ocr"
        spec = importlib.util.spec_from_file_location("weightedai_model", folder / "model.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cfg = json.loads((folder / "config.json").read_text())
        vocab = json.loads((folder / "vocab.json").read_text(encoding="utf-8"))
        self._chars = {int(k): v for k, v in vocab["idx_to_char"].items()}
        self._net = module.CNN_Transformer_OCR(cfg["num_classes"], cfg["d_model"], cfg["nhead"], cfg["num_layers"],
                                              cfg["dropout"])
        state = torch.load(folder / "pytorch_model.bin", map_location="cpu", weights_only=True)
        self._net.load_state_dict(state.get("model_state_dict", state))
        self._net.eval()
        self._torch = torch
        self.name = "weightedai persian_ocr"

    def read(self, image: Image.Image) -> tuple[str, float | None]:
        torch = self._torch
        g = image.convert("L")
        w = min(round(g.width * self.HEIGHT / g.height), self.WIDTH)
        strip = Image.new("L", (self.WIDTH, self.HEIGHT), 255)
        strip.paste(g.resize((w, self.HEIGHT), Image.BICUBIC), (0, 0))
        x = (torch.frombuffer(bytearray(strip.tobytes()), dtype=torch.uint8).float() / 255 - 0.5) / 0.5
        with torch.no_grad():
            probs = self._net(x.view(1, 1, self.HEIGHT, self.WIDTH))[0].exp()
        best, idx = probs.max(1)
        chars, confs, prev = [], [], -1
        for p, i in zip(best.tolist(), idx.tolist()):
            if i != prev and i != 0:
                chars.append(self._chars.get(i, ""))
                confs.append(p)
            prev = i
        return "".join(chars).strip(), round(100 * sum(confs) / len(confs), 1) if confs else None


READERS = {
    "tesseract": lambda: Tesseract("fas"),
    "parisaocr": parisaocr,
    "hezar-crnn": Hezar,
    "weightedai": WeightedAI,
}


def get(name: str) -> Reader:
    if name not in READERS:
        raise ValueError(f"unknown reader {name!r}: one of {', '.join(READERS)}")
    return READERS[name]()
