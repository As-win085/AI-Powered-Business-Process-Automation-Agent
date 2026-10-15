from fastapi import APIRouter

from app.api import (
    anomaly,
    approvals,
    audit,
    auth,
    documents,
    invoices,
    purchase_orders,
    tenants,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(documents.router)
api_router.include_router(invoices.router)
api_router.include_router(purchase_orders.router)
api_router.include_router(anomaly.router)
api_router.include_router(approvals.router)
api_router.include_router(audit.router)

