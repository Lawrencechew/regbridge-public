from app.canonical.models import CanonicalDataType
from app.validation.engine import ValidationEngine
from app.validation.models import (
    ConditionOperator,
    ConditionalRequiredRule,
    SimpleCondition,
    UniqueRule,
)
from tests.validation_helpers import canonical_value, dataset, rule_kwargs, rule_set


def execute(rule, *records):
    return ValidationEngine().validate(dataset(*records), rule_set(rule))


def reference(value):
    return {"reference_number": canonical_value(value, CanonicalDataType.STRING)}


def test_unique_all_unique_and_duplicate_groups() -> None:
    rule = UniqueRule(**rule_kwargs("UNIQUE-001", "reference_number"))
    passing = execute(rule, reference("A"), reference("B"), reference("C"))
    failing = execute(
        rule,
        reference("A"),
        reference("A"),
        reference("B"),
        reference("B"),
        reference("C"),
    )

    assert passing.rule_summaries[0].passed_count == 3
    assert failing.rule_summaries[0].failed_count == 4
    assert [finding.record_id for finding in failing.findings] == [
        "rec-001",
        "rec-002",
        "rec-003",
        "rec-004",
    ]


def test_unique_null_can_be_ignored_or_included() -> None:
    ignored_rule = UniqueRule(
        **rule_kwargs("UNIQUE-NULL-001", "reference_number"), ignore_null=True
    )
    included_rule = UniqueRule(
        **rule_kwargs("UNIQUE-NULL-002", "reference_number"), ignore_null=False
    )
    records = (reference(None), reference(None), reference("A"))

    ignored = execute(ignored_rule, *records).rule_summaries[0]
    included = execute(included_rule, *records).rule_summaries[0]

    assert (ignored.passed_count, ignored.failed_count, ignored.skipped_count) == (1, 0, 2)
    assert (included.passed_count, included.failed_count, included.skipped_count) == (1, 2, 0)


def conditional_rule(operator: ConditionOperator, value=None) -> ConditionalRequiredRule:
    return ConditionalRequiredRule(
        **rule_kwargs(f"CONDITIONAL-{operator.value.upper().replace('_', '-')}", "reference_number"),
        when=SimpleCondition(field_id="status", operator=operator, value=value),
    )


def condition_record(status_marker, reference_marker="missing"):
    values = {}
    if status_marker != "missing":
        values["status"] = canonical_value(status_marker, CanonicalDataType.STRING)
    if reference_marker != "missing":
        values["reference_number"] = canonical_value(
            reference_marker, CanonicalDataType.STRING
        )
    return values


def test_conditional_required_condition_true_present_missing_and_blank() -> None:
    rule = conditional_rule(ConditionOperator.EQUALS, "special")
    report = execute(
        rule,
        condition_record("special", "REF-001"),
        condition_record("special"),
        condition_record("special", "   "),
        condition_record("ordinary"),
    )
    summary = report.rule_summaries[0]

    assert (summary.passed_count, summary.failed_count, summary.skipped_count) == (1, 2, 1)


def test_conditional_equals_not_equals_and_null_operators() -> None:
    cases = [
        (ConditionOperator.EQUALS, "special", "special", 1, 0),
        (ConditionOperator.NOT_EQUALS, "special", "ordinary", 1, 0),
        (ConditionOperator.IS_NULL, None, None, 1, 0),
        (ConditionOperator.IS_NULL, None, "active", 0, 1),
        (ConditionOperator.IS_NOT_NULL, None, "active", 1, 0),
        (ConditionOperator.IS_NOT_NULL, None, None, 0, 1),
    ]
    for operator, expected, status, passed, skipped in cases:
        rule = conditional_rule(operator, expected)
        report = execute(rule, condition_record(status, "REF-001"))
        summary = report.rule_summaries[0]
        assert summary.passed_count == passed
        assert summary.skipped_count == skipped


def test_conditional_missing_condition_field_is_treated_as_null() -> None:
    rule = conditional_rule(ConditionOperator.IS_NULL)
    report = execute(rule, condition_record("missing", "REF-001"))
    assert report.rule_summaries[0].passed_count == 1


def test_unique_handles_ten_thousand_records_with_linear_grouping() -> None:
    rule = UniqueRule(**rule_kwargs("UNIQUE-LARGE-001", "reference_number"))
    records = tuple(reference(f"REF-{index:05d}") for index in range(10_000))
    report = execute(rule, *records)

    assert report.rule_summaries[0].passed_count == 10_000
    assert report.findings == ()
