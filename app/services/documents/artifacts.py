from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from hmac import compare_digest
from pathlib import Path
import re

import pymupdf
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.document import get_user_storage_bytes
from app.models._utils import utc_now
from app.models.document import Document
from app.models.document_artifact import DocumentArtifact
from app.models.tool_job import ToolJob
from app.services.file_storage import resolve_stored_path
from app.services.privacy_detection import PRIVACY_ENGINE_VERSION, scan_pdf

POLICY_VERSION = "1"


class ArtifactError(RuntimeError):
    pass


class ArtifactNotFoundError(ArtifactError):
    pass


class ArtifactNotReadyError(ArtifactError):
    pass


class ArtifactIntegrityError(ArtifactError):
    pass


class ArtifactQuotaError(ArtifactError):
    pass


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def register_protected_artifact(
    db: Session,
    *,
    job: ToolJob,
    source: Path,
    result: Path,
    categories: set[str],
    redaction_mode: str,
    selected_finding_count: int,
    preview_meta: dict,
    generation_meta: dict,
) -> DocumentArtifact:
    if job.source_document_id is None:
        raise ArtifactError("A protected artifact requires a source document")
    if (
        generation_meta.get("flattened") is not True
        or generation_meta.get("selectable_text") is not False
    ):
        raise ArtifactIntegrityError(
            "Protected PDF generation did not produce a flattened image-only copy"
        )
    result_size = result.stat().st_size
    if get_user_storage_bytes(db, job.user_id) + result_size > settings.session_storage_quota_bytes:
        raise ArtifactQuotaError("Storage quota exceeded by the protected copy")

    page_count = int(preview_meta.get("page_count", 0))
    artifact = DocumentArtifact(
        user_id=job.user_id,
        source_document_id=job.source_document_id,
        status="verifying",
        filename=result.name,
        content_type="application/pdf",
        stored_path=str(result.resolve()),
        size_bytes=result_size,
        source_sha256=sha256_file(source),
        artifact_sha256=sha256_file(result),
        privacy_policy={
            "categories": sorted(categories),
            "redaction_mode": redaction_mode,
            "selected_finding_count": selected_finding_count,
            "manual_confirmation": True,
            "flattened": bool(generation_meta.get("flattened", False)),
            "selectable_text": bool(generation_meta.get("selectable_text", True)),
            "render_dpi": generation_meta.get("render_dpi"),
            "image_format": generation_meta.get("image_format"),
            "jpeg_quality": generation_meta.get("jpeg_quality"),
        },
        policy_version=POLICY_VERSION,
        detector_version=str(
            preview_meta.get("engine_version", PRIVACY_ENGINE_VERSION)
        ),
        coverage_report={
            "page_count": page_count,
            "checked_pages": [],
            "unchecked_pages": list(range(1, page_count + 1)),
            "verification_completed": False,
        },
    )
    db.add(artifact)
    db.flush()
    return artifact


def verify_protected_artifact(
    artifact: DocumentArtifact,
    *,
    selected_findings: list[dict],
    progress: Callable[[int, str], None] | None = None,
) -> tuple[str, dict, dict]:
    path = Path(artifact.stored_path)
    if not path.is_file():
        raise ArtifactIntegrityError("Protected artifact file is missing")
    if not compare_digest(sha256_file(path), artifact.artifact_sha256):
        raise ArtifactIntegrityError("Protected artifact hash changed before verification")

    structure, coverage, extracted_text = _inspect_pdf(path, progress)
    categories = set(artifact.privacy_policy.get("categories", []))
    remaining, detector_meta = scan_pdf(
        path,
        categories,
        _detector_progress(progress),
    )
    detector_failures = list(detector_meta.get("detector_failures", []))
    detector_coverage = detector_meta.get("coverage", {})
    detector_unchecked_pages = [
        int(page) for page in detector_coverage.get("unchecked_pages", [])
    ]
    all_unchecked_pages = sorted(
        set(coverage["unchecked_pages"]) | set(detector_unchecked_pages)
    )
    coverage = {
        **coverage,
        "checked_pages": [
            page
            for page in range(1, int(coverage["page_count"]) + 1)
            if page not in all_unchecked_pages
        ],
        "unchecked_pages": all_unchecked_pages,
        "verification_completed": not all_unchecked_pages and not detector_failures,
        "privacy_scan": detector_coverage,
        "detector_failure_count": len(detector_failures),
    }
    residual_ids = _find_residual_selected_text(extracted_text, selected_findings)
    remaining_summary = [
        {
            "page": int(finding.get("page", 0)),
            "group": str(finding.get("group", "")),
            "category": str(finding.get("category", "")),
            "confidence": float(finding.get("confidence", 0)),
        }
        for finding in remaining[:100]
    ]
    risks = _flattening_risks(artifact.privacy_policy, coverage)
    if residual_ids:
        risks.append("selected_text_still_present")
    if remaining:
        risks.append("privacy_findings_remain")
    if structure["unsafe_item_count"]:
        risks.append("unsafe_pdf_structure")
    if detector_failures:
        risks.append("privacy_detector_failed")
    if coverage["unchecked_pages"]:
        risks.append("pages_not_verified")

    verification = {
        "passed": not risks,
        "risks": risks,
        "source_hash_verified": True,
        "artifact_hash_verified": True,
        "selected_text_residual_count": len(residual_ids),
        "selected_text_residual_ids": residual_ids,
        "remaining_finding_count": len(remaining),
        "remaining_findings": remaining_summary,
        "detector_meta": {
            "page_count": int(detector_meta.get("page_count", 0)),
            "categories": list(detector_meta.get("categories", [])),
            "engine_version": str(
                detector_meta.get("engine_version", PRIVACY_ENGINE_VERSION)
            ),
            "failure_count": len(detector_failures),
        },
        "detector_failures": detector_failures,
        "structure": structure,
    }
    status = "ready_for_ai" if not risks else "needs_review"
    return status, coverage, verification


def complete_artifact_verification(
    artifact: DocumentArtifact,
    *,
    status: str,
    coverage_report: dict,
    verification_report: dict,
) -> None:
    if status not in {"ready_for_ai", "needs_review"}:
        raise ValueError("Invalid verification result status")
    artifact.status = status
    artifact.coverage_report = coverage_report
    artifact.verification_report = verification_report
    verified_detector = verification_report.get("detector_meta", {}).get(
        "engine_version"
    )
    if verified_detector:
        artifact.detector_version = str(verified_detector)
    artifact.error_message = None
    artifact.verified_at = utc_now()


def fail_artifact_verification(artifact: DocumentArtifact, error: Exception) -> None:
    artifact.status = "failed"
    artifact.verification_report = {
        "passed": False,
        "risks": ["verification_failed"],
    }
    artifact.error_message = str(error)
    artifact.verified_at = utc_now()


def require_ai_ready_artifact(
    db: Session,
    artifact_id: int,
    user_id: int,
) -> DocumentArtifact:
    artifact = db.scalar(
        select(DocumentArtifact).where(
            DocumentArtifact.id == artifact_id,
            DocumentArtifact.user_id == user_id,
        ).with_for_update()
    )
    if artifact is None:
        raise ArtifactNotFoundError("Document artifact was not found")
    if artifact.status != "ready_for_ai":
        raise ArtifactNotReadyError("Document artifact is not verified for AI use")

    assurance_risks = _flattening_risks(
        artifact.privacy_policy,
        artifact.coverage_report,
    )
    if artifact.policy_version != POLICY_VERSION:
        assurance_risks.append("privacy_policy_version_outdated")
    if artifact.detector_version != PRIVACY_ENGINE_VERSION:
        assurance_risks.append("privacy_detector_version_outdated")
    if artifact.verification_report.get("passed") is not True:
        assurance_risks.append("verification_not_passed")
    if artifact.coverage_report.get("verification_completed") is not True:
        assurance_risks.append("verification_incomplete")
    if assurance_risks:
        artifact.status = "needs_review"
        artifact.error_message = "Protected artifact assurance check failed"
        artifact.verification_report = {
            **artifact.verification_report,
            "passed": False,
            "risks": sorted(
                set(artifact.verification_report.get("risks", []))
                | set(assurance_risks)
            ),
        }
        db.commit()
        raise ArtifactIntegrityError(
            "Document artifact no longer satisfies the protected PDF policy"
        )

    document = db.scalar(
        select(Document).where(
            Document.id == artifact.source_document_id,
            Document.user_id == user_id,
        )
    )
    artifact_path = Path(artifact.stored_path)
    source_path = resolve_stored_path(document.stored_path) if document is not None else None
    try:
        artifact_valid = artifact_path.is_file() and compare_digest(
            sha256_file(artifact_path), artifact.artifact_sha256
        )
        source_valid = (
            source_path is not None
            and source_path.is_file()
            and compare_digest(sha256_file(source_path), artifact.source_sha256)
        )
    except OSError:
        artifact_valid = False
        source_valid = False
    if not artifact_valid or not source_valid:
        artifact.status = "failed"
        artifact.error_message = "Artifact lineage integrity check failed"
        artifact.verification_report = {
            **artifact.verification_report,
            "passed": False,
            "risks": sorted(
                set(artifact.verification_report.get("risks", []))
                | {"integrity_check_failed"}
            ),
        }
        db.commit()
        raise ArtifactIntegrityError("Document artifact integrity check failed")
    return artifact


def delete_artifact(db: Session, artifact: DocumentArtifact) -> None:
    from app.services.ai.jobs import delete_ai_jobs_for_artifacts

    path = Path(artifact.stored_path)
    delete_ai_jobs_for_artifacts(db, [artifact.id])
    db.execute(
        update(ToolJob)
        .where(ToolJob.result_artifact_id == artifact.id)
        .values(
            result_artifact_id=None,
            result_filename=None,
            result_content_type=None,
            result_path=None,
            result_size_bytes=None,
        )
    )
    db.delete(artifact)
    db.commit()
    path.unlink(missing_ok=True)


def minimize_findings(findings: list[dict]) -> list[dict]:
    """Keep review audit geometry while dropping raw detected values."""
    return [
        {
            "id": str(finding.get("id", "")),
            "page": int(finding.get("page", 0)),
            "group": str(finding.get("group", "")),
            "category": str(finding.get("category", "")),
            "text": "",
            "confidence": float(finding.get("confidence", 0)),
            "pdf_rect": list(finding.get("pdf_rect", [])),
            "rect": dict(finding.get("rect", {})),
        }
        for finding in findings
    ]


def _detector_progress(progress):
    if progress is None:
        return None

    def update(percent: int, _stage: str) -> None:
        progress(92 + int(max(0, min(percent, 100)) * 0.06), "verifying")

    return update


def _inspect_pdf(path: Path, progress) -> tuple[dict, dict, str]:
    try:
        with pymupdf.open(path) as document:
            if document.needs_pass or document.page_count < 1:
                raise ArtifactIntegrityError("Protected artifact is not a readable PDF")
            checked_pages: list[int] = []
            unchecked_pages: list[int] = []
            native_text_pages: list[int] = []
            image_only_pages: list[int] = []
            annotation_count = 0
            form_field_count = 0
            link_count = 0
            text_parts: list[str] = []
            for page_index, page in enumerate(document):
                page_number = page_index + 1
                try:
                    page.get_pixmap(matrix=pymupdf.Matrix(0.25, 0.25), alpha=False)
                    page_text = page.get_text()
                    text_parts.append(page_text)
                    if page_text.strip():
                        native_text_pages.append(page_number)
                    else:
                        image_only_pages.append(page_number)
                    annotation_count += _iterable_count(page.annots())
                    form_field_count += _iterable_count(page.widgets())
                    link_count += len(page.get_links())
                    checked_pages.append(page_number)
                except Exception:
                    unchecked_pages.append(page_number)
                if progress:
                    progress(
                        86 + int(((page_index + 1) / max(document.page_count, 1)) * 6),
                        "verifying",
                    )

            metadata_fields = [
                key
                for key in ("title", "author", "subject", "keywords", "creator")
                if str(document.metadata.get(key, "")).strip()
            ]
            embedded_file_count = len(document.embfile_names())
            bookmark_count = len(document.get_toc(simple=True))
            optional_layer_count = len(document.get_ocgs())
            xml_metadata_present = bool(document.get_xml_metadata().strip())
            unsafe_item_count = (
                annotation_count
                + form_field_count
                + link_count
                + embedded_file_count
                + bookmark_count
                + optional_layer_count
                + len(metadata_fields)
                + int(xml_metadata_present)
            )
            structure = {
                "unsafe_item_count": unsafe_item_count,
                "annotation_count": annotation_count,
                "form_field_count": form_field_count,
                "link_count": link_count,
                "embedded_file_count": embedded_file_count,
                "bookmark_count": bookmark_count,
                "optional_layer_count": optional_layer_count,
                "metadata_fields": metadata_fields,
                "xml_metadata_present": xml_metadata_present,
            }
            coverage = {
                "page_count": document.page_count,
                "checked_pages": checked_pages,
                "unchecked_pages": unchecked_pages,
                "native_text_pages": native_text_pages,
                "image_only_pages": image_only_pages,
                "verification_completed": not unchecked_pages,
            }
            return structure, coverage, "\n".join(text_parts)
    except ArtifactIntegrityError:
        raise
    except Exception as error:
        raise ArtifactIntegrityError("Unable to verify the protected PDF") from error


def _iterable_count(items) -> int:
    return 0 if items is None else sum(1 for _ in items)


def _find_residual_selected_text(text: str, findings: list[dict]) -> list[str]:
    normalized_document = _normalize_text(text)
    residual: list[str] = []
    for finding in findings:
        value = _normalize_text(str(finding.get("text", "")))
        if len(value) >= 3 and value in normalized_document:
            residual.append(str(finding.get("id", "")))
    return residual


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _flattening_risks(privacy_policy: dict, coverage_report: dict) -> list[str]:
    risks: list[str] = []
    if privacy_policy.get("flattened") is not True:
        risks.append("protected_pdf_not_flattened")
    if (
        privacy_policy.get("selectable_text") is not False
        or coverage_report.get("native_text_pages")
    ):
        risks.append("selectable_text_present")
    return risks
