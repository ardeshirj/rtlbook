# rtlbook: Tesseract + ParisaOCR's line reader + epubcheck + Python (OCR → EPUB).
#   docker build -f docker/Dockerfile -t rtlbook:dev .
# The final stage is named core, the target other projects build (--target core -t rtlbook:core; make core).
# Build-only tools (curl, unzip, uv) stay in the build stages and don't reach the final image.

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

# ---- Downloads: OCR models, epubcheck, font ----
FROM debian:bookworm-slim AS downloads
ARG EPUBCHECK_VERSION=5.1.0
ARG TESSDATA_LANGS="fas ara osd"  # osd: orientation and script detection (the script check)
ARG PARASTOO_VERSION=2.0.1
ARG LILAK_COMMIT=4f1f426113e764ea099865232fd5e0fa34563c60
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*
# Tesseract "best" (float) models, more accurate than distro packages
RUN mkdir -p /opt/tessdata \
    && for l in $TESSDATA_LANGS; do \
         curl -fsSL -o /opt/tessdata/$l.traineddata \
           https://github.com/tesseract-ocr/tessdata_best/raw/main/$l.traineddata; \
       done
RUN curl -fsSL -o /tmp/epubcheck.zip \
        https://github.com/w3c/epubcheck/releases/download/v${EPUBCHECK_VERSION}/epubcheck-${EPUBCHECK_VERSION}.zip \
    && unzip -q /tmp/epubcheck.zip -d /opt \
    && mv /opt/epubcheck-${EPUBCHECK_VERSION} /opt/epubcheck
# Parastoo (OFL), a book typeface by Saber Rastikerdar, embedded into Persian EPUBs (the "web" cut, with Latin)
RUN curl -fsSL -o /tmp/parastoo.zip \
        https://github.com/rastikerdar/parastoo-font/releases/download/v${PARASTOO_VERSION}/parastoo-font-v${PARASTOO_VERSION}.zip \
    && mkdir -p /opt/fonts \
    && unzip -q -j /tmp/parastoo.zip web/Parastoo.ttf web/Parastoo-Bold.ttf LICENSE -d /opt/fonts \
    && mv /opt/fonts/LICENSE /opt/fonts/OFL.txt
# Lilak (Apache-2.0), a Persian spelling dictionary by Mostafa Sedaghat Joo: its words, the large list for joined words
# (joined.py); the first field of each lexicon line, sorted bytewise (a UTF-8 locale's sort collapses Persian words)
RUN mkdir -p /opt/words \
    && curl -fsSL https://raw.githubusercontent.com/b00f/lilak/${LILAK_COMMIT}/src/data/lexicon \
        | grep -v '^#' | cut -d, -f1 | grep -v '^$' | LC_ALL=C sort -u > /opt/words/lilak-words.txt \
    && curl -fsSL -o /opt/words/LICENSE-lilak.txt https://raw.githubusercontent.com/b00f/lilak/${LILAK_COMMIT}/LICENSE

# ---- ParisaOCR's line reader as an ONNX file: PyTorch and Kraken stay in this stage ----
FROM ${PYTHON_IMAGE} AS parisaocr
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_CACHE_DIR=/tmp/uv-cache
# --torch-backend cpu: PyTorch from its CPU-only index (else a GPU build, gigabytes)
RUN uv venv -q /opt/export && uv pip install -q --python /opt/export/bin/python --torch-backend cpu \
        torch==2.14.0 parisaocr==0.7.2 kraken==7.1.1 onnx onnxruntime==1.31.0 && rm -rf /tmp/uv-cache
COPY docker/parisaocr_onnx.py /tmp/
# The model (Apache-2.0) with ParisaOCR's LICENSE and NOTICE; the export checks itself against the PyTorch model
RUN /opt/export/bin/python /tmp/parisaocr_onnx.py /opt/models/parisaocr 2>&1 | grep -v -i warning \
    && cp /opt/export/lib/python3.12/site-packages/parisaocr-0.7.2.dist-info/licenses/LICENSE \
          /opt/export/lib/python3.12/site-packages/parisaocr-0.7.2.dist-info/licenses/NOTICE /opt/models/parisaocr/

# ---- Python environment, built with uv ----
FROM ${PYTHON_IMAGE} AS venv
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project
COPY src ./src
COPY README.md* LICENSE NOTICE ./
RUN uv sync

# ---- core: OCR and EPUB ----
FROM ${PYTHON_IMAGE} AS core
ENV PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    TESSDATA_PREFIX=/opt/tessdata \
    OMP_THREAD_LIMIT=1 \
    EPUBCHECK_JAR=/opt/epubcheck/epubcheck.jar \
    RTLBOOK_FONTS=/opt/fonts \
    RTLBOOK_WORDS=/opt/words \
    RTLBOOK_MODELS=/opt/models \
    HOME=/tmp
# Tesseract, and Java for epubcheck
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr default-jre-headless \
    && rm -rf /var/lib/apt/lists/*
COPY --from=downloads /opt/tessdata /opt/tessdata
COPY --from=downloads /opt/epubcheck /opt/epubcheck
COPY --from=downloads /opt/fonts /opt/fonts
COPY --from=downloads /opt/words /opt/words
COPY --from=parisaocr /opt/models/parisaocr /opt/models/parisaocr
# Tesseract's own Farsi word list, unpacked from the model: the everyday list for joined words (joined.py)
RUN cd /tmp && combine_tessdata -u /opt/tessdata/fas.traineddata fas. >/dev/null \
    && dawg2wordlist fas.lstm-unicharset fas.lstm-word-dawg words.txt >/dev/null 2>&1 \
    && LC_ALL=C sort -u words.txt > /opt/words/words.txt && rm -f /tmp/fas.* /tmp/words.txt
COPY --from=venv /opt/venv /opt/venv
COPY --from=venv /app /app
WORKDIR /work
ENTRYPOINT ["rtlbook"]
CMD ["--help"]
