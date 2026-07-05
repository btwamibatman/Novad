from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_documents: int
    processed_documents: int
    failed_documents: int
    storage_bytes: int
    detected_languages: dict[str, int]
