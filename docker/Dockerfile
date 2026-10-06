# rtlbook: Tesseract + epubcheck + Python (OCR → EPUB), plus calibre for Kindle KFX packaging.
#   docker build -f docker/Dockerfile -t rtlbook:dev .                  # everything (default)
#   docker build -f docker/Dockerfile --target core -t rtlbook:core .   # no Kindle output: ~680 MB smaller (make core)
# Build-only tools (curl, unzip, uv) stay in the build stages and don't reach the final image.

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

# ---- Downloads: OCR models, epubcheck, font ----
FROM debian:bookworm-slim AS downloads
ARG EPUBCHECK_VERSION=5.1.0
ARG TESSDATA_LANGS="fas ara osd"  # osd: orientation and script detection (the script check)
ARG PARASTOO_VERSION=2.0.1
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

# ---- Python environment, built with uv ----
FROM ${PYTHON_IMAGE} AS venv
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_LINK_MODE=copy UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project
COPY src ./src
COPY README.md* ./
RUN uv sync

# ---- core: OCR and EPUB, no Kindle output ----
FROM ${PYTHON_IMAGE} AS core
ENV PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    TESSDATA_PREFIX=/opt/tessdata \
    OMP_THREAD_LIMIT=1 \
    EPUBCHECK_JAR=/opt/epubcheck/epubcheck.jar \
    RTLBOOK_FONTS=/opt/fonts \
    HOME=/tmp
# Tesseract, and Java for epubcheck
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr default-jre-headless \
    && rm -rf /var/lib/apt/lists/*
COPY --from=downloads /opt/tessdata /opt/tessdata
COPY --from=downloads /opt/epubcheck /opt/epubcheck
COPY --from=downloads /opt/fonts /opt/fonts
COPY --from=venv /opt/venv /opt/venv
COPY --from=venv /app /app
WORKDIR /work
ENTRYPOINT ["rtlbook"]
CMD ["--help"]

# ---- full (default): core + calibre and the KFX Output plugin, for `rtlbook kfx` ----
FROM core AS full
ENV QT_QPA_PLATFORM=offscreen DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends calibre \
    && rm -rf /var/lib/apt/lists/*
# KFX Output plugin (jhowell): packages Kindle Previewer's KPF into a sideloadable .kfx.
# calibre's plugin server uses a self-signed cert that calibre pins, hence its own downloader.
ARG KFX_OUTPUT_PLUGIN=272407
RUN export CALIBRE_CONFIG_DIRECTORY=/opt/calibre-config \
    && calibre-debug -c "from calibre.utils.https import get_https_resource_securely as get; open('/tmp/kfx.zip', 'wb').write(get('https://code.calibre-ebook.com/plugins/${KFX_OUTPUT_PLUGIN}.zip'))" \
    && calibre-customize -a /tmp/kfx.zip && rm /tmp/kfx.zip \
    && chmod -R a+rX /opt/calibre-config
