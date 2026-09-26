from decimal import Decimal

import pytest

from app.canonical.models import CanonicalDataType
from app.reconciliation.engine import ReconciliationEngine
from app.reconciliation.errors import ReconciliationRuleSetConfigurationError
from app.reconciliation.models import (
    AggregateEquationRule,
    AggregateFunction,
    AggregateOperand,
    AggregateTerm,
    ArithmeticOperator,
    GroupedAggregateRule,
)
from tests.reconciliation_helpers import (
    dataset,
    decimal_record,
    rule_kwargs,
    rule_set,
    value,
)


def aggregate_rule(tolerance=Decimal("0"), **overrides):
    values = {
        **rule_kwargs("AGGREGATE-001"),
        "left": (
            AggregateTerm(aggregate=AggregateFunction.SUM, field_id="incoming"),
            AggregateTerm(
                aggregate=AggregateFunction.SUM,
                field_id="outgoing",
                operator=ArithmeticOperator.SUBTRACT,
            ),
        ),
        "right": AggregateOperand(
            aggregate=AggregateFunction.SUM, field_id="declared_change"
        ),
        "tolerance": tolerance,
    }
    values.update(overrides)
    return AggregateEquationRule(**values)


def grouped_rule(**overrides):
    values = {
        **rule_kwargs("GROUPED-001"),
        "group_by": ("category",),
        "left": aggregate_rule().left,
        "right": aggregate_rule().right,
    }
    values.update(overrides)
    return GroupedAggregateRule(**values)


def execute(rule, *records):
    return ReconciliationEngine().reconcile(dataset(*records), rule_set(rule))


def test_aggregate_sum_subtraction_and_tolerance() -> None:
    records = (
        decimal_record("0", "10", "2", "0", declared="8"),
        decimal_record("0", "5", "1", "0", declared="4.01"),
    )
    within = execute(aggregate_rule(Decimal("0.01")), *records)
    exact = execute(aggregate_rule(Decimal("0")), *records)

    assert within.rule_summaries[0].passed_count == 1
    assert exact.findings[0].difference == "0.01"
    assert exact.findings[0].records_considered == 2


def test_aggregate_ignores_null_but_reports_skipped_record_count() -> None:
    records = (
        decimal_record("0", "10", None, "0", declared="10"),
        decimal_record("0", "5", "1", "0", declared="4"),
    )
    report = execute(aggregate_rule(), *records)

    assert report.rule_summaries[0].passed_count == 1


def test_aggregate_empty_or_all_null_dataset_is_skipped() -> None:
    empty = execute(aggregate_rule())
    all_null = execute(
        aggregate_rule(),
        {
            "incoming": value(None, CanonicalDataType.DECIMAL),
            "outgoing": value(None, CanonicalDataType.DECIMAL),
            "declared_change": value(None, CanonicalDataType.DECIMAL),
        },
    )
    assert empty.rule_summaries[0].skipped_count == 1
    assert all_null.rule_summaries[0].skipped_count == 1


def test_count_counts_non_null_values_without_float_arithmetic() -> None:
    rule = AggregateEquationRule(
        **rule_kwargs("COUNT-001"),
        left=(
            AggregateTerm(
                aggregate=AggregateFunction.COUNT, field_id="category"
            ),
        ),
        right=AggregateOperand(
            aggregate=AggregateFunction.COUNT, field_id="declared_change"
        ),
    )
    report = execute(
        rule,
        {
            "category": value("A", CanonicalDataType.STRING),
            "declared_change": value(Decimal("1"), CanonicalDataType.DECIMAL),
        },
    )
    assert report.ready is True


def test_grouped_aggregate_passes_fails_and_keeps_null_group() -> None:
    report = execute(
        grouped_rule(),
        decimal_record("0", "10", "2", "0", category="B", declared="7"),
        decimal_record("0", "5", "1", "0", category="A", declared="4"),
        decimal_record("0", "3", "1", "0", category=None, declared="1"),
    )

    summary = report.rule_summaries[0]
    assert (summary.passed_count, summary.failed_count) == (1, 2)
    assert [finding.group for finding in report.findings] == [
        {"category": "B"},
        {"category": None},
    ]
    assert all(finding.records_considered == 1 for finding in report.findings)
    assert all(finding.source_values == () for finding in report.findings)


def test_multiple_group_fields_are_supported_deterministically() -> None:
    rule = grouped_rule(group_by=("category", "approved"))
    first = decimal_record("0", "2", "0", "0", category="A", declared="1")
    first["approved"] = value(False, CanonicalDataType.BOOLEAN)
    second = decimal_record("0", "2", "0", "0", category="A", declared="1")
    second["approved"] = value(True, CanonicalDataType.BOOLEAN)
    report = execute(rule, second, first)

    assert [finding.group for finding in report.findings] == [
        {"category": "A", "approved": False},
        {"category": "A", "approved": True},
    ]


def test_grouped_aggregate_ignores_null_numeric_values_without_inventing_zero() -> None:
    report = execute(
        grouped_rule(),
        decimal_record("0", "10", None, "0", category="A", declared="10"),
        decimal_record("0", "5", "1", "0", category="A", declared="4"),
    )

    assert report.rule_summaries[0].passed_count == 1
    assert report.findings == ()


def test_unknown_group_and_non_numeric_sum_are_configuration_errors() -> None:
    with pytest.raises(ReconciliationRuleSetConfigurationError):
        execute(grouped_rule(group_by=("unknown_group",)))
    invalid_sum = aggregate_rule(
        left=(
            AggregateTerm(aggregate=AggregateFunction.SUM, field_id="category"),
        )
    )
    with pytest.raises(ReconciliationRuleSetConfigurationError):
        execute(invalid_sum)
