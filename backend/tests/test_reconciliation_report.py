from decimal import Decimal

from app.canonical.models import CanonicalDataset, CanonicalRecord
from app.reconciliation.engine import ReconciliationEngine
from app.validation.errors import DatasetNotStructurallyValidError
from app.validation.models import RuleSeverity
from tests.reconciliation_helpers import (
    dataset,
    decimal_record,
    reconciliation_schema,
    row_rule,
    rule_set,
)


def test_ready_semantics_and_summary_counts() -> None:
    passing = row_rule(id="PASS-001")
    review = row_rule(id="REVIEW-001", severity=RuleSeverity.REVIEW)
    blocking = row_rule(id="BLOCKING-001")
    data = dataset(decimal_record("10", "5", "2", "12"))

    review_only = ReconciliationEngine().reconcile(data, rule_set(review))
    mixed = ReconciliationEngine().reconcile(data, rule_set(blocking, review))
    all_pass = ReconciliationEngine().reconcile(
        dataset(decimal_record("10", "5", "2", "13")), rule_set(passing)
    )

    assert all_pass.ready is True
    assert review_only.ready is True
    assert mixed.ready is False
    assert mixed.summary.blocking_findings == 1
    assert mixed.summary.review_findings == 1


def test_structurally_invalid_dataset_stops_reconciliation() -> None:
    invalid = CanonicalDataset(
        dataset_id="invalid",
        schema=reconciliation_schema(),
        records=[
            CanonicalRecord(record_id="duplicate", values={}),
            CanonicalRecord(record_id="duplicate", values={}),
        ],
    )
    try:
        ReconciliationEngine().reconcile(invalid, rule_set(row_rule()))
    except DatasetNotStructurallyValidError as error:
        assert error.result.valid is False
    else:
        raise AssertionError("Expected structural validation to stop reconciliation")


def test_report_fingerprint_is_deterministic_and_excludes_timestamp() -> None:
    data = dataset(decimal_record("10", "5", "2", "12"))
    rules = rule_set(row_rule())
    first = ReconciliationEngine().reconcile(data, rules)
    second = ReconciliationEngine().reconcile(data, rules)

    assert first.fingerprint == second.fingerprint
    assert first.findings == second.findings
    assert first.evaluated_at != second.evaluated_at


def test_changed_value_rule_or_version_changes_fingerprint() -> None:
    engine = ReconciliationEngine()
    original = engine.reconcile(
        dataset(decimal_record("10", "5", "2", "12")), rule_set(row_rule())
    )
    changed_value = engine.reconcile(
        dataset(decimal_record("10", "5", "2", "11")), rule_set(row_rule())
    )
    changed_rule = engine.reconcile(
        dataset(decimal_record("10", "5", "2", "12")),
        rule_set(row_rule(tolerance=Decimal("0.1"))),
    )
    changed_version = engine.reconcile(
        dataset(decimal_record("10", "5", "2", "12")),
        rule_set(row_rule(), version="1.1.0"),
    )

    assert len(
        {
            original.fingerprint,
            changed_value.fingerprint,
            changed_rule.fingerprint,
            changed_version.fingerprint,
        }
    ) == 4
