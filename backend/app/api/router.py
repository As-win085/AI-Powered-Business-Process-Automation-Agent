from fastapi import APIRouter

from app.api import audit, auth, documents, invoices, tenants

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(documents.router)
api_router.include_router(invoices.router)
api_router.include_router(audit.router)

