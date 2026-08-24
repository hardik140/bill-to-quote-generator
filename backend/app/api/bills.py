from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.bill import EXTRACTION_COMPLETED
from app.repositories import bill_repository, scenario_repository
from app.schemas.bill import (
    BillItemCreate,
    BillItemOut,
    BillItemUpdate,
    BillOut,
    ConfirmResponse,
    ItemReorderRequest,
)
from app.schemas.scenario import ScenarioOut
from app.services.calculation_service import compute_bill_totals, compute_line
from app.services.validation_service import ValidationError, validate_quantity, validate_rate

router = APIRouter(prefix="/api/bills", tags=["bills"])


def _get_bill_or_404(db: Session, bill_id: str):
    bill = bill_repository.get(db, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    return bill


def _recalculate_bill_totals(bill) -> None:
    line_results = [
        compute_line(item.quantity, item.source_rate, item.gst_rate) for item in bill.items
    ]
    totals = compute_bill_totals(line_results)
    bill.subtotal = totals.subtotal
    bill.tax_total = totals.tax_total
    bill.grand_total = totals.grand_total


@router.get("/{bill_id}", response_model=BillOut)
def get_bill(bill_id: str, db: Session = Depends(get_db)) -> BillOut:
    bill = _get_bill_or_404(db, bill_id)
    return BillOut.model_validate(bill)


@router.post("/{bill_id}/items", response_model=BillItemOut)
def add_item(bill_id: str, payload: BillItemCreate, db: Session = Depends(get_db)) -> BillItemOut:
    bill = _get_bill_or_404(db, bill_id)
    if bill.confirmed:
        raise HTTPException(status_code=409, detail="Confirmed bills cannot be edited.")

    try:
        rate = validate_rate(payload.rate)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    quantity = Decimal("1")
    gst_rate = Decimal("0")
    line_result = compute_line(quantity, rate, gst_rate)
    next_serial = (max((i.serial_no for i in bill.items), default=0)) + 1

    item = bill_repository.add_item(
        db,
        bill,
        serial_no=next_serial,
        description=payload.description,
        hsn_sac=None,
        gst_rate=gst_rate,
        quantity=quantity,
        unit=None,
        source_rate=rate,
        taxable_rate=rate,
        line_amount=line_result.line_amount,
        tax_amount=line_result.tax_amount,
        total_amount=line_result.total_amount,
        confidence=Decimal("1.0000"),
        user_verified=True,
    )
    db.flush()
    db.refresh(bill)
    _recalculate_bill_totals(bill)
    db.commit()
    db.refresh(item)
    return BillItemOut.model_validate(item)


@router.put("/{bill_id}/items/{item_id}", response_model=BillItemOut)
def update_item(
    bill_id: str, item_id: str, payload: BillItemUpdate, db: Session = Depends(get_db)
) -> BillItemOut:
    bill = _get_bill_or_404(db, bill_id)
    if bill.confirmed:
        raise HTTPException(status_code=409, detail="Confirmed bills cannot be edited.")

    item = bill_repository.get_item(db, item_id)
    if item is None or item.bill_id != bill_id:
        raise HTTPException(status_code=404, detail="Item not found.")

    if payload.description is not None:
        item.description = payload.description
    if payload.rate is not None:
        try:
            rate = validate_rate(payload.rate)
        except ValidationError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=exc.message) from exc
        item.source_rate = rate
        item.taxable_rate = rate

    quantity = item.quantity if item.quantity and item.quantity > 0 else Decimal("1")
    gst_rate = item.gst_rate if item.gst_rate is not None else Decimal("0")
    line_result = compute_line(quantity, item.source_rate, gst_rate)
    item.line_amount = line_result.line_amount
    item.tax_amount = line_result.tax_amount
    item.total_amount = line_result.total_amount
    item.user_verified = True

    db.flush()
    _recalculate_bill_totals(bill)
    db.commit()
    db.refresh(item)
    return BillItemOut.model_validate(item)


@router.delete("/{bill_id}/items/{item_id}", status_code=204)
def delete_item(bill_id: str, item_id: str, db: Session = Depends(get_db)) -> None:
    bill = _get_bill_or_404(db, bill_id)
    if bill.confirmed:
        raise HTTPException(status_code=409, detail="Confirmed bills cannot be edited.")

    item = bill_repository.get_item(db, item_id)
    if item is None or item.bill_id != bill_id:
        raise HTTPException(status_code=404, detail="Item not found.")

    bill_repository.delete_item(db, item)
    db.refresh(bill)
    _recalculate_bill_totals(bill)
    db.commit()


@router.put("/{bill_id}/items/reorder", response_model=list[BillItemOut])
def reorder_items(
    bill_id: str, payload: ItemReorderRequest, db: Session = Depends(get_db)
) -> list[BillItemOut]:
    bill = _get_bill_or_404(db, bill_id)
    if bill.confirmed:
        raise HTTPException(status_code=409, detail="Confirmed bills cannot be edited.")

    items_by_id = {item.id: item for item in bill.items}
    if set(payload.item_ids_in_order) != set(items_by_id.keys()):
        raise HTTPException(status_code=400, detail="item_ids_in_order must include every item exactly once.")

    for idx, item_id in enumerate(payload.item_ids_in_order, start=1):
        items_by_id[item_id].serial_no = idx

    db.commit()
    db.refresh(bill)
    return [BillItemOut.model_validate(i) for i in sorted(bill.items, key=lambda i: i.serial_no)]


@router.post("/{bill_id}/confirm", response_model=ConfirmResponse)
def confirm_bill(bill_id: str, db: Session = Depends(get_db)) -> ConfirmResponse:
    bill = _get_bill_or_404(db, bill_id)

    if not bill.items:
        raise HTTPException(status_code=400, detail="Cannot confirm a bill with no line items.")

    for item in bill.items:
        try:
            validate_quantity(item.quantity)
            validate_rate(item.source_rate)
        except ValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Item '{item.description}': {exc.message}",
            ) from exc

    bill.confirmed = True
    bill.extraction_status = EXTRACTION_COMPLETED
    db.commit()
    return ConfirmResponse(bill_id=bill.id, confirmed=True)


@router.get("/{bill_id}/scenarios", response_model=list[ScenarioOut])
def list_bill_scenarios(bill_id: str, db: Session = Depends(get_db)) -> list[ScenarioOut]:
    _get_bill_or_404(db, bill_id)
    scenarios = scenario_repository.list_for_bill(db, bill_id)
    return [ScenarioOut.model_validate(s) for s in scenarios]
