"""Line readers: one printed line's image in, its text and confidence out (ROADMAP.md "Reader slot and scorecard").

`convert` reads a scan's lines through this slot (`pipeline.read_lines`: Tesseract finds the lines, each is cut and
read alone, by ParisaOCR unless told otherwise) and an exported PDF's whole pages in Tesseract's one call
(`ocr.ocr_lines`); the scorecard (`rtlbook bench`) scores each reader on checked lines. Tesseract and ParisaOCR are in
rtlbook's image; the others are open models measured for the scorecard, in a separate image
(`docker/Dockerfile.readers`).
"""

from __future__ import annotations

import json
import os
import re
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
        """The line's text, words in reading order, and a confidence (0–100) or None. Readers convert uses give it on
        Tesseract's scale, the one its thresholds are tuned to; the scorecard's other readers on their own."""
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


class ParisaOCR:
    """ParisaOCR's line reader (Apache-2.0, Ali Javadi): PaddleOCR's PP-OCRv6 recognizer design trained with Kraken on
    Persian print, run by ONNX Runtime from the file `docker/parisaocr_onnx.py` makes in the image (no PyTorch, no
    Kraken). Kraken's steps for a line, redone: 96 pixels high, 16 white columns at each end, inverted; then a margin
    of white instead of the 2560 columns of padding the model was trained with (the ONNX file adds them back by
    calculation); greedy CTC; display order to reading order (Kraken's bidi, copied in `rtlbook.bidi`); ParisaOCR's
    own clean-up of each word. The same text as ParisaOCR's reader on the scorecard's test lines, 2.7 times faster.
    Its confidence is put on Tesseract's scale, which convert's thresholds are tuned to (DESIGN.md §4.5)."""

    HEIGHT, PAD, MARGIN = 96, 16, 128
    PLACEHOLDER = "\u00a6"  # what the model writes for ZWNJ (Kraken's bidi would drop a ZWNJ, kraken#809)

    def __init__(self, folder: Path | None = None):
        import onnxruntime as ort

        folder = folder or Path(os.environ.get("RTLBOOK_MODELS", "/opt/models")) / "parisaocr"
        options = ort.SessionOptions()
        options.intra_op_num_threads = int(os.environ.get("OMP_THREAD_LIMIT", "0"))  # pages run side by side
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(str(folder / "parisaocr.onnx"), options,
                                             providers=["CPUExecutionProvider"])
        self._chars = {int(k): v for k, v in json.loads((folder / "codec.json").read_text(encoding="utf-8")).items()}
        self.name = "parisaocr fa-0.1 onnx"  # the model docker/Dockerfile's parisaocr stage exports

    @staticmethod
    def tesseract_scale(conf: float) -> float:
        """ParisaOCR's confidence on Tesseract's scale. ParisaOCR's crowds near 100: on the 1932 book's checked train
        lines its lines below 96 have 12% or more letters wrong, as Tesseract's do below 70, and from 98 up almost
        none. A straight line through those: 95 -> 50, 97 -> 70, 99 -> 90."""
        return round(max(0.0, 100 - 10 * (100 - conf)), 1)

    def read(self, image: Image.Image) -> tuple[str, float | None]:
        import numpy as np

        g = image.convert("L").convert("RGB")
        w = int(g.width * self.HEIGHT / g.height)
        if w < 1:
            return "", None
        n = w + 2 * self.PAD
        line = np.full((self.HEIGHT, n, 3), 255, np.uint8)
        line[:, self.PAD:self.PAD + w] = np.asarray(g.resize((w, self.HEIGHT), Image.LANCZOS))
        x = np.zeros((self.HEIGHT, -(-(n + self.MARGIN) // 32) * 32, 3), np.float32)  # 0: white, once inverted
        x[:, :n] = 1 - line / 255
        probs, olens = self._session.run(None, {"image": x.transpose(2, 0, 1)[None],
                                                "lens": np.array([n], np.int64)})
        p = probs[0, :, :int(olens[0])]
        chars, confs, prev = [], [], 0
        for label, c in zip(p.argmax(0).tolist(), p.max(0).tolist()):
            if label and label != prev:
                chars.append(self._chars.get(label, ""))
                confs.append(c)
            elif label:
                confs[-1] = max(confs[-1], c)
            prev = label
        words = _reading_order_words("".join(chars), confs, self.PLACEHOLDER)
        if not words:
            return "", None
        return (_canonical(" ".join(t for t, _ in words)),
                self.tesseract_scale(round(sum(c for _, c in words) / len(words), 1)))


def _reading_order_words(display: str, confs: list[float], placeholder: str) -> list[tuple[str, float]]:
    """A line in display order (left to right, as a line reader sees it) -> its words in reading order, each with its
    confidence (0-100, the mean of its letters'). A line with more Latin than Arabic-script letters reads left to
    right, any other right to left. ZWNJ is kept: swapped for a neutral the bidi algorithm leaves in place."""
    import unicodedata

    from rtlbook.bidi import get_display_map

    zwnj = "\u200c"
    display = display.replace(placeholder, zwnj)
    if not display.strip():
        return []
    latin = sum(1 for c in display if c.isalpha() and unicodedata.bidirectional(c) == "L")
    arabic = sum(1 for c in display if unicodedata.bidirectional(c) in ("R", "AL"))
    text, order = get_display_map(display.replace(zwnj, placeholder), base_dir="L" if latin > arabic else "R")
    words, cur = [], []
    for ch, i in zip(text.replace(placeholder, zwnj), order):
        if ch.isspace():
            if cur:
                words.append(cur)
            cur = []
        else:
            cur.append((ch, i))
    if cur:
        words.append(cur)
    out = []
    for word in words:
        if t := _canonical("".join(c for c, _ in word)):
            out.append((t, round(100 * sum(confs[i] for _, i in word) / len(word), 1)))
    return out


# ParisaOCR's text clean-up (parisaocr/fa_text.py, canonical(); Apache-2.0, Ali Javadi), for the same text as its
# reader: Arabic yeh and kaf, Arabic-Indic digits, presentation forms, bidi controls and tatweel fixed; ZWNJ, Persian
# vs Latin digits, diacritics and Persian punctuation kept.
_BIDI_CONTROLS = "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff"
_CANON = str.maketrans({"\u064a": "\u06cc", "\u0649": "\u06cc", "\u0643": "\u06a9", "\u06d5": "\u0647",
                        "\u0640": None, "\u2026": "...",
                        **{d: "-" for d in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"},
                        **{chr(0x0660 + i): chr(0x06F0 + i) for i in range(10)},
                        **{c: None for c in _BIDI_CONTROLS}})
_PRESENTATION_FORMS = re.compile("[\ufb50-\ufdff\ufe70-\ufeff]")
_DASH_TATWEEL = re.compile("(?<![\u0620-\u065f\u066e-\u06d3\u06d5\u06fa-\u06ff])\u0640+")


def _canonical(text: str) -> str:
    import unicodedata

    zwnj = "\u200c"
    text = _PRESENTATION_FORMS.sub(lambda m: unicodedata.normalize("NFKC", m.group()), text)
    text = _DASH_TATWEEL.sub("-", unicodedata.normalize("NFC", text)).translate(_CANON)
    text = re.sub(f"\u0647{zwnj}?\u0654", "\u06c0", text)
    text = re.sub(f"{zwnj}+", zwnj, text)
    text = re.sub(f"{zwnj}(?=\\s|$)|(?<=\\s){zwnj}|^{zwnj}", "", text, flags=re.M)
    lines = (re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


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
    "parisaocr": ParisaOCR,
    "hezar-crnn": Hezar,
    "weightedai": WeightedAI,
}


def get(name: str) -> Reader:
    if name not in READERS:
        raise ValueError(f"unknown reader {name!r}: one of {', '.join(READERS)}")
    return READERS[name]()
