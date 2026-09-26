from datetime import date, datetime
from decimal import Decimal

import pytest

from app.canonical.models import CanonicalDataType
from app.validation.engine import ValidationEngine
from app.validation.models import (
    AllowedCharactersRule,
    DecimalPlacesRule,
    EnumRule,
    MaximumRule,
    MinimumRule,
    NotBlankRule,
    RegexRule,
    RequiredRule,
    RuleOutcome,
)
from tests.validation_helpers import canonical_value, dataset, rule_kwargs, rule_set


def execute(rule, *records):
    return ValidationEngine().validate(dataset(*records), rule_set(rule))


def test_required_distinguishes_missing_from_present_null() -> None:
    rule = RequiredRule(**rule_kwargs("REQUIRED-001", "description"))
    report = execute(
        rule,
        {},
        {"description": canonical_value(None, CanonicalDataType.STRING)},
    )

    assert report.rule_summaries[0].failed_count == 1
    assert report.rule_summaries[0].passed_count == 1


@pytest.mark.parametrize(
    ("value", "data_type", "passes"),
    [
        (None, CanonicalDataType.STRING, False),
        ("", CanonicalDataType.STRING, False),
        ("   ", CanonicalDataType.STRING, False),
        ("hello", CanonicalDataType.STRING, True),
        (0, CanonicalDataType.INTEGER, True),
        (Decimal("0"), CanonicalDataType.DECIMAL, True),
        (False, CanonicalDataType.BOOLEAN, True),
    ],
)
def test_not_blank_semantics(value, data_type, passes: bool) -> None:
    field_id = {
        CanonicalDataType.STRING: "description",
        CanonicalDataType.INTEGER: "sequence",
        CanonicalDataType.DECIMAL: "quantity",
        CanonicalDataType.BOOLEAN: "approved",
    }[data_type]
    rule = NotBlankRule(**rule_kwargs("NOT-BLANK-001", field_id))
    report = execute(rule, {field_id: canonical_value(value, data_type)})

    assert (report.rule_summaries[0].passed_count == 1) is passes


def test_enum_is_case_sensitive_and_skips_null() -> None:
    rule = EnumRule(
        **rule_kwargs("ENUM-001", "status"), allowed_values=("active", "inactive")
    )
    report = execute(
        rule,
        {"status": canonical_value("active", CanonicalDataType.STRING)},
        {"status": canonical_value("Active", CanonicalDataType.STRING)},
        {"status": canonical_value("unknown", CanonicalDataType.STRING)},
        {"status": canonical_value(None, CanonicalDataType.STRING)},
    )
    summary = report.rule_summaries[0]

    assert (summary.passed_count, summary.failed_count, summary.skipped_count) == (1, 2, 1)


@pytest.mark.parametrize(
    ("field_id", "data_type", "boundary", "below", "at", "above"),
    [
        ("sequence", CanonicalDataType.INTEGER, 10, 9, 10, 11),
        ("quantity", CanonicalDataType.DECIMAL, Decimal("10"), Decimal("9"), Decimal("10"), Decimal("11")),
        ("transaction_date", CanonicalDataType.DATE, date(2026, 8, 14), date(2026, 8, 13), date(2026, 8, 14), date(2026, 8, 15)),
        ("processed_at", CanonicalDataType.DATETIME, datetime(2026, 8, 14, 9), datetime(2026, 8, 14, 8), datetime(2026, 8, 14, 9), datetime(2026, 8, 14, 10)),
    ],
)
def test_minimum_and_maximum_inclusive_and_exclusive(
    field_id, data_type, boundary, below, at, above
) -> None:
    minimum = MinimumRule(
        **rule_kwargs("MIN-001", field_id), minimum=boundary, inclusive=True
    )
    maximum = MaximumRule(
        **rule_kwargs("MAX-001", field_id), maximum=boundary, inclusive=False
    )
    minimum_report = execute(
        minimum,
        {field_id: canonical_value(below, data_type)},
        {field_id: canonical_value(at, data_type)},
        {field_id: canonical_value(None, data_type)},
    )
    maximum_report = execute(
        maximum,
        {field_id: canonical_value(below, data_type)},
        {field_id: canonical_value(at, data_type)},
        {field_id: canonical_value(above, data_type)},
    )

    assert (
        minimum_report.rule_summaries[0].passed_count,
        minimum_report.rule_summaries[0].failed_count,
        minimum_report.rule_summaries[0].skipped_count,
    ) == (1, 1, 1)
    assert (
        maximum_report.rule_summaries[0].passed_count,
        maximum_report.rule_summaries[0].failed_count,
    ) == (1, 2)


@pytest.mark.parametrize(
    ("value", "passes"),
    [
        (Decimal("10"), True),
        (Decimal("10.1"), True),
        (Decimal("10.10"), True),
        (Decimal("10.123"), False),
        (Decimal("-1.20"), True),
    ],
)
def test_decimal_places_counts_scale_including_trailing_zeroes(value, passes: bool) -> None:
    rule = DecimalPlacesRule(
        **rule_kwargs("PLACES-001", "quantity"), maximum_places=2
    )
    report = execute(rule, {"quantity": canonical_value(value, CanonicalDataType.DECIMAL)})
    assert (report.rule_summaries[0].passed_count == 1) is passes


def test_regex_matches_full_string_and_skips_null() -> None:
    rule = RegexRule(
        **rule_kwargs("REGEX-001", "description"), pattern=r"^[A-Z]{3}[0-9]{2}$"
    )
    report = execute(
        rule,
        {"description": canonical_value("ABC12", CanonicalDataType.STRING)},
        {"description": canonical_value("ABC123", CanonicalDataType.STRING)},
        {"description": canonical_value(None, CanonicalDataType.STRING)},
    )
    summary = report.rule_summaries[0]
    assert (summary.passed_count, summary.failed_count, summary.skipped_count) == (1, 1, 1)


def test_allowed_characters_reports_invalid_characters_and_allows_empty() -> None:
    rule = AllowedCharactersRule(
        **rule_kwargs("CHARS-001", "description"),
        allowed_characters="ABC123",
    )
    report = execute(
        rule,
        {"description": canonical_value("ABC123", CanonicalDataType.STRING)},
        {"description": canonical_value("AB!", CanonicalDataType.STRING)},
        {"description": canonical_value("A!?", CanonicalDataType.STRING)},
        {"description": canonical_value("", CanonicalDataType.STRING)},
        {"description": canonical_value(None, CanonicalDataType.STRING)},
    )
    summary = report.rule_summaries[0]

    assert (summary.passed_count, summary.failed_count, summary.skipped_count) == (2, 2, 1)
    assert "'!'" in report.findings[0].message
    assert "'?'" in report.findings[1].message
