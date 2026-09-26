from decimal import Decimal

from app.canonical.models import CanonicalDataType, SourceReference
from app.reconciliation.engine import ReconciliationEngine
from app.reconciliation.models import ArithmeticOperator, FieldOperand, FieldTerm
from tests.reconciliation_helpers import (
    dataset,
    decimal_record,
    row_rule,
    rule_set,
    value,
)


def execute(rule, *records):
    return ReconciliationEngine().reconcile(dataset(*records), rule_set(rule))


def test_row_equation_exact_within_and_outside_tolerance() -> None:
    report = execute(
        row_rule(Decimal("0.01")),
        decimal_record("10", "5", "2", "13"),
        decimal_record("10", "5", "2", "13.01"),
        decimal_record("10", "5", "2", "13.011"),
    )
    summary = report.rule_summaries[0]
    assert (summary.passed_count, summary.failed_count) == (2, 1)


def test_row_difference_uses_actual_minus_expected_for_both_signs() -> None:
    report = execute(
        row_rule(),
        decimal_record("10", "5", "2", "14"),
        decimal_record("10", "5", "2", "12"),
    )
    assert [finding.difference for finding in report.findings] == ["1", "-1"]


def test_null_operand_skips_without_treating_null_as_zero() -> None:
    report = execute(row_rule(), decimal_record("10", None, "2", "8"))
    summary = report.rule_summaries[0]
    assert summary.skipped_count == 1
    assert summary.evaluated_count == 0
    assert report.findings == ()


def test_integer_and_mixed_integer_decimal_arithmetic_is_exact() -> None:
    integer_rule = row_rule(
        left=(
            FieldTerm(field_id="integer_opening"),
            FieldTerm(field_id="integer_incoming"),
        ),
        right=FieldOperand(field_id="integer_closing"),
    )
    integer_report = execute(
        integer_rule,
        {
            "integer_opening": value(10, CanonicalDataType.INTEGER),
            "integer_incoming": value(5, CanonicalDataType.INTEGER),
            "integer_closing": value(15, CanonicalDataType.INTEGER),
        },
    )
    mixed_rule = row_rule(
        left=(
            FieldTerm(field_id="integer_opening"),
            FieldTerm(field_id="incoming", operator=ArithmeticOperator.ADD),
        ),
        right=FieldOperand(field_id="closing_balance"),
    )
    mixed_report = execute(
        mixed_rule,
        {
            "integer_opening": value(10, CanonicalDataType.INTEGER),
            "incoming": value(Decimal("0.10"), CanonicalDataType.DECIMAL),
            "closing_balance": value(Decimal("10.10"), CanonicalDataType.DECIMAL),
        },
    )
    assert integer_report.ready is True
    assert mixed_report.ready is True


def test_row_failure_preserves_all_participating_provenance_and_rule_sources() -> None:
    source = SourceReference(source_name="example.csv", row=2, column="Opening")
    record = decimal_record("10", "5", "2", "12")
    record["opening_balance"] = value(
        Decimal("10"), CanonicalDataType.DECIMAL, source
    )
    report = execute(row_rule(source_refs=("SRC-001",)), record)
    finding = report.findings[0]

    assert finding.source_refs == ("SRC-001",)
    assert [item.field_id for item in finding.source_values] == [
        "opening_balance",
        "incoming",
        "outgoing",
        "closing_balance",
    ]
    assert finding.source_values[0].source == source
