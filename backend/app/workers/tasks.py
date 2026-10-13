import uuid

from app.db.models import Document
from app.db.session import SessionLocal
from app.services import document_service
from app.workers.celery_app import celery_app


@celery_app.task(
    name="app.workers.tasks.process_document",
    bind=True,
    max_retries=3,
    acks_late=True,
)
def process_document_task(
    self,
    document_id: str,
) -> str:
    """Run text extraction (with OCR fallback) for a stored document.

    Permanent document failures (corrupt/password-protected/etc.) are recorded on
    the document itself and do not retry. Retries only cover unexpected errors.
    """
    db = SessionLocal()
    try:
        document = db.get(Document, uuid.UUID(document_id))
        if document is None:
            return "not_found"
        document_service.process_document(db, tenant_id=document.tenant_id, document_id=document.id)
        return "ok"
    except Exception as exc:  # noqa: BLE001 - retry on unexpected worker errors
        db.rollback()
        raise self.retry(exc=exc, countdown=self.default_retry_delay) from exc
    finally:
        db.close()
