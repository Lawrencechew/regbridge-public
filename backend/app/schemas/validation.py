from pydantic import BaseModel


class ValidationRuleTypesResponse(BaseModel):
    rule_types: list[str]
