# rtlbook: Tesseract + epubcheck + Calibre (Kindle AZW3 / KFX packaging); no PyTorch engines.
# Build with --build-arg WITH_CALIBRE=0 for a smaller image without Kindle output.
FROM python:3.12-slim-bookworm

ARG EPUBCHECK_VERSION=5.1.0
ARG TESSDATA_LANGS="fas ara"
ARG VAZIRMATN_VERSION=33.003
ARG WITH_CALIBRE=1

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache \
    PATH=/opt/venv/bin:$PATH \
    TESSDATA_PREFIX=/opt/tessdata \
    OMP_THREAD_LIMIT=1 \
    EPUBCHECK_JAR=/opt/epubcheck/epubcheck.jar \
    RTLBOOK_FONTS=/opt/fonts \
    QT_QPA_PLATFORM=offscreen \
    HOME=/tmp

RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr default-jre-headless curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

# Calibre's ebook-convert: EPUB -> AZW3 for sideloading to Kindle (runs locally, no upload)
RUN if [ "$WITH_CALIBRE" = "1" ]; then \
        apt-get update && apt-get install -y --no-install-recommends calibre \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# KFX Output plugin (jhowell): packages Kindle Previewer's KPF into a sideloadable .kfx.
# calibre's plugin server uses a self-signed cert that calibre pins, hence its own downloader.
ARG KFX_OUTPUT_PLUGIN=272407
RUN if [ "$WITH_CALIBRE" = "1" ]; then \
        export CALIBRE_CONFIG_DIRECTORY=/opt/calibre-config \
        && calibre-debug -c "from calibre.utils.https import get_https_resource_securely as get; open('/tmp/kfx.zip', 'wb').write(get('https://code.calibre-ebook.com/plugins/${KFX_OUTPUT_PLUGIN}.zip'))" \
        && calibre-customize -a /tmp/kfx.zip && rm /tmp/kfx.zip \
        && chmod -R a+rX /opt/calibre-config; \
    fi

# Tesseract "best" (float) models, more accurate than distro packages
RUN mkdir -p $TESSDATA_PREFIX \
    && for l in osd $TESSDATA_LANGS; do \
         curl -fsSL -o $TESSDATA_PREFIX/$l.traineddata \
           https://github.com/tesseract-ocr/tessdata_best/raw/main/$l.traineddata; \
       done

RUN curl -fsSL -o /tmp/epubcheck.zip \
        https://github.com/w3c/epubcheck/releases/download/v${EPUBCHECK_VERSION}/epubcheck-${EPUBCHECK_VERSION}.zip \
    && unzip -q /tmp/epubcheck.zip -d /opt \
    && mv /opt/epubcheck-${EPUBCHECK_VERSION} /opt/epubcheck \
    && rm /tmp/epubcheck.zip

# Vazirmatn (OFL) embedded into Persian EPUBs
RUN curl -fsSL -o /tmp/vz.zip \
        https://github.com/rastikerdar/vazirmatn/releases/download/v${VAZIRMATN_VERSION}/vazirmatn-v${VAZIRMATN_VERSION}.zip \
    && mkdir -p /opt/fonts \
    && unzip -q -j /tmp/vz.zip fonts/ttf/Vazirmatn-Regular.ttf fonts/ttf/Vazirmatn-Bold.ttf OFL.txt -d /opt/fonts \
    && rm /tmp/vz.zip

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project
COPY src ./src
COPY README.md* ./
RUN uv sync && chmod -R a+rX /opt/venv

WORKDIR /work
ENTRYPOINT ["rtlbook"]
CMD ["--help"]
