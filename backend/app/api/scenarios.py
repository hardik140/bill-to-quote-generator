from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.scenario import ROUNDING_NEAREST_1, ROUNDING_NEAREST_5, ROUNDING_NEAREST_10, ROUNDING_NONE
from app.repositories import bill_repository, generated_file_repository, scenario_repository
from app.schemas.scenario import ScenarioConfigRequest, ScenarioCreateResponse, ScenarioOut, ScenarioPdfResponse
from app.services.pdf_service import generate_scenario_pdf, hash_file
from app.services.scenario_service import build_all_scenarios
from app.services.validation_service import ValidationError

router = APIRouter(prefix="/api", tags=["scenarios"])

VALID_ROUNDING_MODES = {ROUNDING_NONE, ROUNDING_NEAREST_1, ROUNDING_NEAREST_5, ROUNDING_NEAREST_10}


@router.post("/bills/{bill_id}/scenarios", response_model=ScenarioCreateResponse)
def create_scenarios(
    bill_id: str, payload: ScenarioConfigRequest, db: Session = Depends(get_db)
) -> ScenarioCreateResponse:
    bill = bill_repository.get(db, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")
    if not bill.confirmed:
        raise HTTPException(status_code=409, detail="Bill must be confirmed before generating scenarios.")
    if payload.rounding not in VALID_ROUNDING_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid rounding mode '{payload.rounding}'.")

    try:
        scenarios = build_all_scenarios(
            bill,
            payload.scenario_b_markup_percent,
            payload.scenario_c_markup_percent,
            payload.rounding,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    for scenario in scenarios:
        scenario_repository.add(db, scenario)
    db.commit()

    return ScenarioCreateResponse(scenario_ids=[s.id for s in scenarios])


@router.get("/scenarios/{scenario_id}", response_model=ScenarioOut)
def get_scenario(scenario_id: str, db: Session = Depends(get_db)) -> ScenarioOut:
    scenario = scenario_repository.get(db, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    return ScenarioOut.model_validate(scenario)


@router.post("/scenarios/{scenario_id}/pdf", response_model=ScenarioPdfResponse)
def generate_pdf(scenario_id: str, db: Session = Depends(get_db)) -> ScenarioPdfResponse:
    scenario = scenario_repository.get(db, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found.")
    bill = bill_repository.get(db, scenario.bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found.")

    pdf_path = generate_scenario_pdf(bill, scenario)
    file_hash = hash_file(pdf_path)

    record = generated_file_repository.create(
        db,
        scenario_id=scenario.id,
        file_type="pdf",
        filename=pdf_path.name,
        storage_path=str(pdf_path),
        file_hash=file_hash,
    )
    db.commit()

    return ScenarioPdfResponse(
        scenario_id=scenario.id,
        filename=record.filename,
        storage_path=record.storage_path,
        file_hash=record.file_hash,
    )
