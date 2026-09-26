from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.reconciliation.engine import ReconciliationEngine
from app.reconciliation.errors import ReconciliationRuleSetConfigurationError
from app.reconciliation.models import FieldOperand, FieldTerm, ReconciliationRuleSet
from tests.reconciliation_helpers import dataset, row_rule, rule_kwargs, rule_set


def test_rule_id_version_duplicates_and_non_empty_rules_are_validated() -> None:
    assert row_rule(id="TEST-BALANCE-001").id == "TEST-BALANCE-001"
    with pytest.raises(ValidationError):
        row_rule(id="bad_rule")
    with pytest.raises(ValidationError):
        rule_set(row_rule(), row_rule())
    with pytest.raises(ValidationError):
        ReconciliationRuleSet(
            id="EXAMPLE-RECONCILIATION", version="1.0", name="Example", rules=(row_rule(),)
        )
    with pytest.raises(ValidationError):
        ReconciliationRuleSet(
            id="EXAMPLE-RECONCILIATION", version="1.0.0", name="Example", rules=()
        )


def test_empty_expression_and_negative_tolerance_are_rejected() -> None:
    with pytest.raises(ValidationError):
        row_rule(left=())
    with pytest.raises(ValidationError):
        row_rule(tolerance=Decimal("-0.01"))


@pytest.mark.parametrize(
    ("left_field", "right_field"),
    [("unknown", "closing_balance"), ("opening_balance", "unknown")],
)
def test_unknown_operand_fields_are_configuration_errors(left_field, right_field) -> None:
    rule = row_rule(
        left=(FieldTerm(field_id=left_field),),
        right=FieldOperand(field_id=right_field),
    )
    with pytest.raises(ReconciliationRuleSetConfigurationError):
        ReconciliationEngine().reconcile(dataset(), rule_set(rule))


def test_boolean_arithmetic_is_configuration_error() -> None:
    rule = row_rule(
        left=(FieldTerm(field_id="approved"),),
        right=FieldOperand(field_id="closing_balance"),
    )
    with pytest.raises(ReconciliationRuleSetConfigurationError):
        ReconciliationEngine().reconcile(dataset(), rule_set(rule))
