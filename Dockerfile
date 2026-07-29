FROM node:24-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV STANZA_RESOURCES_DIR=/opt/stanza_resources

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-noto \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-kaz \
        tesseract-ocr-osd \
        tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

RUN python -c "import stanza; [stanza.download(lang, model_dir='/opt/stanza_resources', processors='tokenize,ner', verbose=False) for lang in ('kk', 'ru', 'en')]"

COPY . .
COPY --from=frontend-build /app/web/dist /app/app/web/dist

RUN adduser --disabled-password --gecos "" --no-create-home appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
