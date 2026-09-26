from fastapi import APIRouter

from app.schemas.validation import ValidationRuleTypesResponse
from app.validation.models import RuleType

router = APIRouter(prefix="/validation", tags=["validation"])


@router.get("/rule-types", response_model=ValidationRuleTypesResponse)
def list_validation_rule_types() -> ValidationRuleTypesResponse:
    return ValidationRuleTypesResponse(
        rule_types=sorted(rule_type.value for rule_type in RuleType)
    )
