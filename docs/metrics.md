# Project Metrics & CV Bullets

Real figures extracted directly from the source code and architecture.
Use these when writing your CV/resume bullets for this project.

---

## Hard Numbers from the Code

### Document & Upload Limits
| Parameter | Value | Source |
|---|---|---|
| Max file size | **50 MB** | `config.py: max_upload_size_bytes = 50 * 1024 * 1024` |
| Max pages per document | **40 pages** | `config.py: max_pdf_pages = 40` |
| Per-user storage quota | **500 MB** | `config.py: session_storage_quota_bytes = 500 * 1024 * 1024` |
| Max request size | **55 MB** | `config.py: max_request_size_bytes` |

### OCR Pipeline Parameters
| Parameter | Value | Source |
|---|---|---|
| OCR render DPI | **300 DPI** | `config.py: ocr_render_dpi = 300` |
| Minimum acceptable DPI | **180 DPI** | `config.py: ocr_min_render_dpi = 180` |
| Max pixels per page | **20 megapixels** | `config.py: ocr_max_pixels_per_page = 20_000_000` |
| OCR confidence threshold (high) | **85%** | `config.py: ocr_high_confidence = 85.0` |
| OCR mean confidence minimum | **70%** | `config.py: ocr_min_mean_confidence = 70.0` |
| Max low-confidence word ratio | **25%** | `config.py: ocr_max_low_confidence_ratio = 0.25` |
| OCR candidate similarity threshold | **90%** | `config.py: ocr_candidate_similarity = 0.90` |
| OCR languages supported | **3 (Russian, Kazakh, English)** | `config.py: ocr_languages = "rus+kaz+eng"` |
| Page OCR timeout | **45 seconds** | `config.py: ocr_page_timeout_seconds = 45` |
| Max table cell retries (per page) | **20** | `text_analysis.py: MAX_CELL_RETRIES = 20` |
| Max targeted OCR retries | **12** | `text_analysis.py: MAX_TARGETED_RETRIES = 12` |

### Text Chunking & Retrieval
| Parameter | Value | Source |
|---|---|---|
| Chunk size | **1 600 characters** | `chunks.py: CHUNK_MAX_CHARS = 1600` |
| Chunk overlap | **150 characters** | `chunks.py: CHUNK_OVERLAP_CHARS = 150` |
| Top-K chunks for Q&A | **5 chunks** | `chunks.py: RETRIEVAL_TOP_K = 5` |
| Max retrieval context | **8 000 characters** | `chunks.py: RETRIEVAL_MAX_CHARS = 8000` |
| Embedding batch size | **16 chunks** | `retrieval.py` (batched embed loop) |
| In-memory vector cache size | **512 vectors** | `retrieval.py: while len(_vectors) > 512` |

### AI & Analysis
| Parameter | Value | Source |
|---|---|---|
| Q&A retrieval methods | **2 (BM25 + hybrid semantic RRF)** | `retrieval.py` |
| Q&A context window (Ollama) | **16 384 tokens** | `config.py: ollama_context_length = 16384` |
| AI job max retries | **4 attempts** | `config.py: ai_job_max_attempts = 4` |
| AI timeout per request | **45 seconds** | `config.py: ai_request_timeout_seconds = 45` |
| AI chat timeout | **20 seconds** | `config.py: ai_chat_timeout_seconds = 20` |
| Max key points per analysis | **20** | `local_document.py: points[:20]` |
| Max findings per analysis | **100** | `local_document.py: findings[:100]` |
| Max analysis pages (layout) | **3 pages** | `config.py: layout_review_max_pages = 3` |
| Layout DPI | **150 DPI** | `config.py: layout_review_dpi = 150` |
| Summary max input | **12 000 chars** | `config.py: ai_summary_max_chars = 12000` |
| Content review batch | **10 000 chars** | `config.py: content_review_batch_max_chars = 10000` |
| Max review batches | **6** | `config.py: content_review_thorough_max_batches = 6` |

### PII / Privacy Detection
| Parameter | Value | Source |
|---|---|---|
| PII NER languages | **3 (Kazakh, Russian, English)** | `config.py: pii_ner_languages = "kk,ru,en"` |
| PII entity categories detected | **20+** | `privacy_detection.py: PRIVACY_TAXONOMY` |
| Detection methods | **5 types** | Presidio rules, Stanza NER, regex (IIN/BIN/IBAN), image (faces/signatures/QR/barcode) |
| Kazakh-specific entities | **IIN, BIN, IBAN** | `privacy_detection.py` custom recognizers |
| PDF redaction modes | **2 (black fill + pseudonym labels)** | `redaction.py` |

### Compression
| Ghostscript mode | Color DPI | Mono DPI | JPEG Quality |
|---|---|---|---|
| Recommended | 150 | 300 | 80% |
| Extreme | 96 | 200 | 55% |

---

## Ready-to-Use CV Bullets

### Short / Impact-first style

- Built a multilingual document processing API (Python/FastAPI) with **Tesseract OCR across Russian, Kazakh, and English**, processing PDFs up to **40 pages / 50 MB** with adaptive 300 DPI rendering and dual-pass confidence scoring (>=70% mean threshold)
- Implemented a **hybrid BM25 + semantic search** Q&A pipeline using Ollama embeddings and reciprocal-rank fusion over **1 600-char overlapping chunks** with a bounded **512-vector in-memory cache** to avoid redundant inference
- Designed a **privacy-first redaction workflow** detecting **20+ PII entity types** (including Kazakh IIN/BIN/IBAN, faces, QR codes, and signatures) across **3 languages** via Presidio rules + Stanza NER; redacted PDFs are rebuilt as image-only artifacts and re-verified by OCR before any AI upload
- Delivered **3 PDF compression modes** (lossless via PyMuPDF, 150 DPI balanced via Ghostscript, 96 DPI extreme) with automatic fallback to the original file if the output is larger
- Engineered an **async document analysis worker** with PostgreSQL row-locking to prevent duplicate execution, **4-attempt retry logic** with exponential backoff, and stale-job cleanup
- Implemented table-aware OCR: OpenCV grid detection -> per-cell Tesseract re-scan (up to **20 targeted retries per page**) -> markdown table reconstruction with [UNCERTAIN_OCR] flags for low-confidence cells

### Longer / detail style

- Architected a **full-stack document intelligence system** (Vue 3 + FastAPI + PostgreSQL) that extracts native text or falls back to multi-language Tesseract OCR (rus+kaz+eng) at **300 DPI**, applies adaptive CLAHE preprocessing and optional secondary thresholded pass, then selects the higher-scoring candidate using a weighted mean confidence metric; dual-pass agreement below **90% similarity** marks pages as needing manual review
- Built a **chunk-based Q&A engine** that splits extracted text into **1 600-character overlapping segments** (150-char overlap), retrieves the top-5 relevant chunks via **BM25 + cosine-similarity RRF** (Qwen embedding model, 16-item batch), and feeds up to **8 000 characters** of context to a local Qwen 3.5-4B LLM for evidence-backed answers with source page citations
- Engineered a **zero-leakage PII pipeline**: Presidio + Stanza NER detects **20+ entity types** across KK/RU/EN, pseudonymises all spans before AI inference, and restores original values from a per-session token map; any unknown placeholder in the AI response aborts the request (fail-closed)
- Created a **verified protected-document workflow**: redaction -> image-only PDF rebuild (strips selectable text & hidden objects) -> automatic OCR re-verification -> needs_review / ready_for_ai gating -> structured AI job with **4 retries**, cancellation support, and automatic remote-file cleanup after analysis

---

## Quick Reference: Suggested inline phrasing

| Topic | Suggested phrasing |
|---|---|
| OCR accuracy | "dual-pass Tesseract OCR with >=70% mean confidence threshold and per-cell retry (up to 20 retries/page)" |
| Languages | "3 languages (Russian, Kazakh, English)" |
| Q&A retrieval | "hybrid BM25 + embedding retrieval with reciprocal-rank fusion across 1 600-char chunks" |
| Throughput limit | "documents up to 40 pages / 50 MB per upload" |
| PII types | "20+ PII entity categories including KZ-specific IIN, BIN, IBAN" |
| Compression | "PDF size reduction via 3 compression modes (lossless / 150 DPI / 96 DPI extreme)" |
| Reliability | "4-attempt retry with exponential backoff; PostgreSQL row-locking prevents duplicate worker execution" |
| Cache | "512-entry LRU vector cache eliminating redundant embedding calls" |
