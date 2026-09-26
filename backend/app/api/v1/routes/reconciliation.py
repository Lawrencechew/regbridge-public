from fastapi import APIRouter

from app.reconciliation.models import ReconciliationRuleType
from app.schemas.reconciliation import ReconciliationRuleTypesResponse

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


@router.get("/rule-types", response_model=ReconciliationRuleTypesResponse)
def list_reconciliation_rule_types() -> ReconciliationRuleTypesResponse:
    return ReconciliationRuleTypesResponse(
        rule_types=sorted(rule_type.value for rule_type in ReconciliationRuleType)
    )
