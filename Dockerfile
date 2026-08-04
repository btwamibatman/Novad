# syntax=docker/dockerfile:1

FROM node:24-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim

ARG PIP_VERSION=26.2

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV STANZA_RESOURCES_DIR=/opt/stanza_resources

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-noto \
        ghostscript \
        libreoffice-writer \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-kaz \
        tesseract-ocr-osd \
        tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-torch-cpu.txt requirements-ml.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install "pip==${PIP_VERSION}" \
    && python -m pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        -r requirements-torch-cpu.txt \
    && python -m pip install -r requirements-ml.txt \
    && python -m pip check

RUN --mount=type=cache,target=/root/.cache/huggingface \
    python -c "import stanza; [stanza.download(lang, model_dir='/opt/stanza_resources', processors='tokenize,ner', verbose=False) for lang in ('kk', 'ru', 'en')]"

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -r requirements.txt \
    && python -m pip check

COPY . .
COPY --from=frontend-build /app/web/dist /app/app/web/dist

RUN adduser --disabled-password --gecos "" --no-create-home appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
