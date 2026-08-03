from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Document Processing API"
    environment: Literal["development", "production"] = "development"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    database_url: str = "sqlite:///./documents.db"
    storage_dir: str = "storage/uploads"
    max_upload_size_bytes: int = 50 * 1024 * 1024
    max_request_size_bytes: int = 55 * 1024 * 1024
    max_pdf_pages: int = 100
    session_cookie_name: str = "document_session"
    session_ttl_minutes: int = 120
    session_cleanup_interval_seconds: int = 900
    session_storage_quota_bytes: int = 500 * 1024 * 1024
    ai_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_thinking_budget: int = 0
    ai_summary_max_chars: int = 12000
    ai_summary_max_output_tokens: int = 1800
    ai_chat_timeout_seconds: int = 20
    ai_request_timeout_seconds: int = 45
    content_review_quick_max_chars: int = 50000
    content_review_batch_max_chars: int = 10000
    content_review_thorough_max_batches: int = 6
    content_review_max_output_tokens: int = 1800
    layout_review_max_pages: int = 3
    layout_review_dpi: int = 150
    layout_review_min_dpi: int = 72
    layout_review_max_output_tokens: int = 1000
    layout_review_max_pixels_per_page: int = 8_000_000
    layout_review_max_inline_bytes: int = 12 * 1024 * 1024
    ocr_languages: str = "rus+kaz+eng"
    ocr_min_text_signal_chars: int = 30
    ocr_render_dpi: int = 300
    ocr_min_render_dpi: int = 180
    ocr_max_pixels_per_page: int = 20_000_000
    ocr_min_mean_confidence: float = 70.0
    ocr_high_confidence: float = 85.0
    ocr_low_word_confidence: float = 60.0
    ocr_max_low_confidence_ratio: float = 0.25
    ocr_candidate_similarity: float = 0.90
    ocr_page_timeout_seconds: int = 45
    analysis_worker_poll_seconds: float = 1.0
    pii_masking_enabled: bool = True
    pii_ner_languages: str = "kk,ru,en"
    pii_model_dir: str = "/opt/stanza_resources"

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if not self.allowed_host_list:
            raise ValueError("ALLOWED_HOSTS must contain at least one host")
        if any("://" in host or "/" in host for host in self.allowed_host_list):
            raise ValueError("ALLOWED_HOSTS entries must be hostnames without scheme or path")
        if self.is_production and (
            "*" in self.allowed_host_list
            or set(self.allowed_host_list) <= {"localhost", "127.0.0.1", "testserver"}
        ):
            raise ValueError("Production requires an explicit public ALLOWED_HOSTS value")
        if self.max_upload_size_bytes <= 0:
            raise ValueError("MAX_UPLOAD_SIZE_BYTES must be greater than zero")
        if self.max_request_size_bytes <= self.max_upload_size_bytes:
            raise ValueError(
                "MAX_REQUEST_SIZE_BYTES must be greater than MAX_UPLOAD_SIZE_BYTES "
                "to allow multipart overhead"
            )
        if self.max_pdf_pages <= 0:
            raise ValueError("MAX_PDF_PAGES must be greater than zero")
        if self.ocr_render_dpi <= 0:
            raise ValueError("OCR_RENDER_DPI must be greater than zero")
        if self.ocr_min_render_dpi <= 0 or self.ocr_min_render_dpi > self.ocr_render_dpi:
            raise ValueError(
                "OCR_MIN_RENDER_DPI must be positive and not exceed OCR_RENDER_DPI"
            )
        if self.ocr_max_pixels_per_page <= 0:
            raise ValueError("OCR_MAX_PIXELS_PER_PAGE must be greater than zero")
        if self.ocr_page_timeout_seconds <= 0:
            raise ValueError("OCR_PAGE_TIMEOUT_SECONDS must be greater than zero")
        if self.analysis_worker_poll_seconds <= 0:
            raise ValueError("ANALYSIS_WORKER_POLL_SECONDS must be greater than zero")
        if self.is_production and not self.session_cookie_name.startswith("__Host-"):
            self.session_cookie_name = f"__Host-{self.session_cookie_name}"
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip().lower() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def pii_ner_language_list(self) -> list[str]:
        return [
            language.strip().lower()
            for language in self.pii_ner_languages.split(",")
            if language.strip()
        ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
