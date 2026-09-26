from pydantic import BaseModel


class ReconciliationRuleTypesResponse(BaseModel):
    rule_types: list[str]
