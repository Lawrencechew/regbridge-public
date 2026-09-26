from app.canonical.models import (
    CanonicalDataType,
    CanonicalDataset,
    CanonicalRecord,
    SourceReference,
)
from app.validation.engine import ValidationEngine
from app.validation.errors import DatasetNotStructurallyValidError
from app.validation.models import (
    EnumRule,
    NotBlankRule,
    RuleSeverity,
)
from tests.validation_helpers import (
    canonical_value,
    dataset,
    rule_kwargs,
    rule_set,
    validation_schema,
)


def test_report_ready_and_summary_for_blocking_review_and_skipped_checks() -> None:
    blocking = NotBlankRule(**rule_kwargs("BLOCKING-001", "description"))
    review = EnumRule(
        **rule_kwargs("REVIEW-001", "status", RuleSeverity.REVIEW),
        allowed_values=("active", "inactive"),
    )
    report = ValidationEngine().validate(
        dataset(
            {
                "description": canonical_value("", CanonicalDataType.STRING),
                "status": canonical_value("unknown", CanonicalDataType.STRING),
            },
            {
                "description": canonical_value("valid", CanonicalDataType.STRING),
                "status": canonical_value(None, CanonicalDataType.STRING),
            },
        ),
        rule_set(blocking, review),
    )

    assert report.valid is True
    assert report.ready is False
    assert report.summary.model_dump() == {
        "rules": 2,
        "blocking_findings": 1,
        "review_findings": 1,
        "passed_checks": 1,
        "skipped_checks": 1,
    }


def test_review_findings_do_not_prevent_readiness() -> None:
    review = NotBlankRule(
        **rule_kwargs("REVIEW-001", "description", RuleSeverity.REVIEW)
    )
    report = ValidationEngine().validate(
        dataset({"description": canonical_value(None, CanonicalDataType.STRING)}),
        rule_set(review),
    )
    assert report.ready is True


def test_findings_follow_rule_then_record_order_and_preserve_provenance() -> None:
    first = NotBlankRule(
        **rule_kwargs("FIRST-001", "description"), source_refs=("SRC-001",)
    )
    second = EnumRule(
        **rule_kwargs("SECOND-001", "status"), allowed_values=("active",)
    )
    source = SourceReference(source_name="example.csv", row=2, column="Description")
    report = ValidationEngine().validate(
        dataset(
            {
                "description": canonical_value("", CanonicalDataType.STRING, source),
                "status": canonical_value("bad", CanonicalDataType.STRING),
            },
            {
                "description": canonical_value("", CanonicalDataType.STRING),
                "status": canonical_value("bad", CanonicalDataType.STRING),
            },
        ),
        rule_set(first, second),
    )

    assert [(finding.rule_id, finding.record_id) for finding in report.findings] == [
        ("FIRST-001", "rec-001"),
        ("FIRST-001", "rec-002"),
        ("SECOND-001", "rec-001"),
        ("SECOND-001", "rec-002"),
    ]
    assert report.findings[0].source == source
    assert report.findings[0].source_refs == ("SRC-001",)


def test_structurally_invalid_dataset_is_rejected_without_findings() -> None:
    invalid_dataset = CanonicalDataset(
        dataset_id="dataset-invalid",
        schema=validation_schema(),
        records=[
            CanonicalRecord(record_id="duplicate", values={}),
            CanonicalRecord(record_id="duplicate", values={}),
        ],
    )
    rule = NotBlankRule(**rule_kwargs("RULE-001", "description"))

    try:
        ValidationEngine().validate(invalid_dataset, rule_set(rule))
    except DatasetNotStructurallyValidError as error:
        assert error.result.valid is False
        assert error.result.issues[0].code == "DUPLICATE_RECORD_ID"
    else:
        raise AssertionError("Expected structural validation to stop rule execution")


def test_same_inputs_produce_same_results_and_report_fingerprint() -> None:
    data = dataset({"description": canonical_value("", CanonicalDataType.STRING)})
    rules = rule_set(NotBlankRule(**rule_kwargs("RULE-001", "description")))
    first = ValidationEngine().validate(data, rules)
    second = ValidationEngine().validate(data, rules)

    assert first.findings == second.findings
    assert first.rule_summaries == second.rule_summaries
    assert first.report_fingerprint == second.report_fingerprint
    assert first.evaluated_at != second.evaluated_at
