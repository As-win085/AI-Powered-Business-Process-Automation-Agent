"""Tenant-scoped purchase order management (CRUD + CSV import).

Purchase orders are the reference documents that invoices are matched against
in :mod:`app.services.po_matching_service`. Nothing here authorizes payment;
it only maintains the reference data used for review.
"""
from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import PurchaseOrder, PurchaseOrderItem, Supplier
from app.schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderImportError,
    PurchaseOrderImportResult,
    PurchaseOrderItemData,
)


class PurchaseOrderError(ValueError):
    """Raised for purchase order validation problems."""


_PO_STATUSES = {"open", "closed", "cancelled"}


def normalize_po_number(value: str | None) -> str | None:
    """Normalize a PO number so ``PO-00123`` and ``po 123`` compare equal."""
    from app.services.duplicate_detection import normalize_invoice_number

    return normalize_invoice_number(value)


def resolve_supplier(
    db: Session, tenant_id: uuid.UUID, name: str | None, tax_id: str | None = None
) -> Supplier | None:
    """Find or create a supplier by normalized name within the tenant."""
    from app.services.duplicate_detection import normalize_supplier_name

    if not name:
        return None
    normalized = normalize_supplier_name(name)
    supplier = db.scalars(
        select(Supplier).where(
            Supplier.tenant_id == tenant_id, Supplier.normalized_name == normalized
        )
    ).first()
    if supplier is None:
        supplier = Supplier(
            tenant_id=tenant_id,
            name=name.strip(),
            normalized_name=normalized,
            tax_identifier=tax_id,
        )
        db.add(supplier)
        db.flush()
    return supplier


def _get_or_none(
    db: Session, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> PurchaseOrder | None:
    return db.scalars(
        select(PurchaseOrder).where(
            PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.id == po_id
        )
    ).first()


def _attach_items(
    db: Session, tenant_id: uuid.UUID, po: PurchaseOrder
) -> PurchaseOrder:
    """Expose line items on ``po`` so API responses can serialize them."""
    po.line_items = list(
        db.scalars(
            select(PurchaseOrderItem)
            .where(
                PurchaseOrderItem.tenant_id == tenant_id,
                PurchaseOrderItem.purchase_order_id == po.id,
            )
            .order_by(PurchaseOrderItem.line_number, PurchaseOrderItem.id)
        ).all()
    )
    return po


def get_purchase_order(
    db: Session, tenant_id: uuid.UUID, po_id: uuid.UUID
) -> PurchaseOrder | None:
    po = _get_or_none(db, tenant_id, po_id)
    return _attach_items(db, tenant_id, po) if po is not None else None


def _replace_items(
    db: Session,
    tenant_id: uuid.UUID,
    po: PurchaseOrder,
    items: list[PurchaseOrderItemData] | None,
) -> None:
    for existing in db.scalars(
        select(PurchaseOrderItem).where(
            PurchaseOrderItem.tenant_id == tenant_id,
            PurchaseOrderItem.purchase_order_id == po.id,
        )
    ).all():
        db.delete(existing)
    db.flush()

    for index, item in enumerate(items or [], start=1):
        line_number = item.line_number if item.line_number is not None else index
        quantity = item.quantity
        unit_price = item.unit_price
        line_total = item.line_total
        if line_total is None and quantity is not None and unit_price is not None:
            line_total = (quantity * unit_price).quantize(Decimal("0.01"))
        db.add(
            PurchaseOrderItem(
                tenant_id=tenant_id,
                purchase_order_id=po.id,
                line_number=line_number,
                description=item.description,
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
            )
        )


def _find_duplicate_number(
    db: Session, tenant_id: uuid.UUID, po_number: str, exclude_id: uuid.UUID | None = None
) -> PurchaseOrder | None:
    """Return a tenant PO whose number collides with ``po_number`` when normalized."""
    normalized = normalize_po_number(po_number)
    conditions = [PurchaseOrder.tenant_id == tenant_id]
    if exclude_id is not None:
        conditions.append(PurchaseOrder.id != exclude_id)
    rows = list(db.scalars(select(PurchaseOrder).where(*conditions)).all())
    for row in rows:
        if row.po_number == po_number:
            return row
        if normalized is not None and normalize_po_number(row.po_number) == normalized:
            return row
    return None


def create_purchase_order(
    db: Session, tenant_id: uuid.UUID, payload: PurchaseOrderCreate
) -> PurchaseOrder:
    if _find_duplicate_number(db, tenant_id, payload.po_number) is not None:
        raise PurchaseOrderError(f"Purchase order {payload.po_number!r} already exists")

    supplier = resolve_supplier(
        db, tenant_id, payload.supplier_name, payload.supplier_tax_id
    )
    po = PurchaseOrder(
        tenant_id=tenant_id,
        supplier_id=supplier.id if supplier else None,
        po_number=payload.po_number.strip(),
        currency=payload.currency.upper(),
        total_amount=payload.total_amount,
        status=payload.status,
    )
    db.add(po)
    db.flush()
    _replace_items(db, tenant_id, po, payload.line_items)
    db.flush()
    return _attach_items(db, tenant_id, po)


def update_purchase_order(
    db: Session, tenant_id: uuid.UUID, po: PurchaseOrder, payload: dict
) -> PurchaseOrder:
    if "po_number" in payload and payload["po_number"]:
        new_number = payload["po_number"].strip()
        clash = _find_duplicate_number(db, tenant_id, new_number, exclude_id=po.id)
        if clash is not None:
            raise PurchaseOrderError(f"Purchase order {new_number!r} already exists")
        po.po_number = new_number

    if "supplier_name" in payload or "supplier_tax_id" in payload:
        supplier = resolve_supplier(
            db,
            tenant_id,
            payload.get("supplier_name"),
            payload.get("supplier_tax_id"),
        )
        if supplier is not None:
            po.supplier_id = supplier.id

    if payload.get("currency"):
        po.currency = str(payload["currency"]).upper()
    if "total_amount" in payload:
        po.total_amount = payload["total_amount"]
    if payload.get("status"):
        po.status = payload["status"]

    if payload.get("line_items") is not None:
        _replace_items(
            db,
            tenant_id,
            po,
            [PurchaseOrderItemData(**item) for item in payload["line_items"]],
        )
    db.flush()
    return _attach_items(db, tenant_id, po)


def delete_purchase_order(db: Session, tenant_id: uuid.UUID, po: PurchaseOrder) -> None:
    # Line items cascade at the database level via the composite FK.
    db.delete(po)
    db.flush()


def list_purchase_orders(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    status: str | None = None,
    supplier_id: uuid.UUID | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[PurchaseOrder]]:
    conditions = [PurchaseOrder.tenant_id == tenant_id]
    if status:
        conditions.append(PurchaseOrder.status == status)
    if supplier_id:
        conditions.append(PurchaseOrder.supplier_id == supplier_id)
    if query:
        conditions.append(PurchaseOrder.po_number.ilike(f"%{query}%"))

    total = db.scalar(
        select(func.count()).select_from(PurchaseOrder).where(*conditions)
    ) or 0
    rows = list(
        db.scalars(
            select(PurchaseOrder)
            .where(*conditions)
            .order_by(PurchaseOrder.po_number)
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return int(total), [_attach_items(db, tenant_id, po) for po in rows]


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def import_purchase_orders_csv(
    db: Session, tenant_id: uuid.UUID, content: bytes
) -> PurchaseOrderImportResult:
    """Import POs from a CSV where each row is one PO line item.

    Expected columns: ``po_number`` (required), ``supplier_name``,
    ``currency``, ``total_amount``, ``status``, ``line_number``,
    ``description``, ``quantity``, ``unit_price``, ``line_total``. Rows sharing
    a ``po_number`` are grouped into one purchase order.
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise PurchaseOrderError("CSV file is empty or missing a header row")

    grouped: dict[str, dict] = {}
    errors: list[PurchaseOrderImportError] = []
    order: list[str] = []

    for row_index, row in enumerate(reader, start=2):
        po_number = (row.get("po_number") or "").strip()
        if not po_number:
            errors.append(
                PurchaseOrderImportError(row=row_index, message="missing po_number")
            )
            continue
        if row_index == 2 and po_number.lower() == "po_number":
            continue
        if po_number not in grouped:
            grouped[po_number] = {
                "supplier_name": (row.get("supplier_name") or "").strip() or None,
                "currency": (row.get("currency") or "USD").strip().upper(),
                "total_amount": _decimal_or_none(row.get("total_amount")),
                "status": (row.get("status") or "open").strip().lower() or "open",
                "line_items": [],
            }
            order.append(po_number)
        entry = grouped[po_number]
        if entry["supplier_name"] is None and row.get("supplier_name"):
            entry["supplier_name"] = row["supplier_name"].strip()
        if entry["total_amount"] is None:
            entry["total_amount"] = _decimal_or_none(row.get("total_amount"))

        description = (row.get("description") or "").strip() or None
        quantity = _decimal_or_none(row.get("quantity"))
        unit_price = _decimal_or_none(row.get("unit_price"))
        line_total = _decimal_or_none(row.get("line_total"))
        line_number = row.get("line_number")
        parsed_line_number: int | None = None
        if line_number not in (None, ""):
            try:
                parsed_line_number = int(str(line_number).strip())
            except ValueError:
                parsed_line_number = None
        if description or quantity is not None or unit_price is not None or line_total is not None:
            entry["line_items"].append(
                PurchaseOrderItemData(
                    line_number=parsed_line_number,
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )

    skipped: list[str] = []
    created = 0
    for po_number in order:
        entry = grouped[po_number]
        if _find_duplicate_number(db, tenant_id, po_number.strip()) is not None:
            skipped.append(po_number)
            continue
        currency = str(entry["currency"] or "USD").strip().upper()[:3] or "USD"
        status_value = (
            entry["status"] if entry["status"] in _PO_STATUSES else "open"
        )
        create_purchase_order(
            db,
            tenant_id,
            PurchaseOrderCreate(
                po_number=po_number.strip(),
                supplier_name=entry["supplier_name"],
                currency=currency,
                total_amount=entry["total_amount"],
                status=status_value,
                line_items=entry["line_items"] or None,
            ),
        )
        created += 1

    db.flush()
    return PurchaseOrderImportResult(created=created, skipped=skipped, errors=errors)


def load_po_items(
    db: Session, tenant_id: uuid.UUID, po_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[PurchaseOrderItem]]:
    if not po_ids:
        return {}
    rows = db.scalars(
        select(PurchaseOrderItem)
        .where(
            PurchaseOrderItem.tenant_id == tenant_id,
            PurchaseOrderItem.purchase_order_id.in_(po_ids),
        )
        .order_by(PurchaseOrderItem.line_number)
    ).all()
    grouped: dict[uuid.UUID, list[PurchaseOrderItem]] = {}
    for item in rows:
        grouped.setdefault(item.purchase_order_id, []).append(item)
    return grouped
