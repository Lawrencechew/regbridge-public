import hashlib
import json
import logging
from datetime import UTC, datetime

from app.canonical.fingerprint import dataset_fingerprint
from app.canonical.models import CanonicalDataType, CanonicalDataset
from app.canonical.validation import CanonicalStructuralValidator
from app.reconciliation.errors import ReconciliationRuleSetConfigurationError
from app.reconciliation.evaluators import (
    AggregateEquationEvaluator,
    GroupedAggregateEvaluator,
    ReconciliationEvaluation,
    ReconciliationEvaluator,
    RowEquationEvaluator,
)
from app.reconciliation.models import (
    AggregateEquationRule,
    AggregateFunction,
    GroupedAggregateRule,
    ReconciliationFinding,
    ReconciliationReport,
    ReconciliationReportSummary,
    ReconciliationRule,
    ReconciliationRuleSet,
    ReconciliationRuleSummary,
    ReconciliationRuleType,
    RowEquationRule,
)
from app.validation.errors import DatasetNotStructurallyValidError
from app.validation.models import RuleOutcome, RuleSeverity

logger = logging.getLogger(__name__)


class ReconciliationEngine:
    def __init__(self) -> None:
        self._structural_validator = CanonicalStructuralValidator()
        self._evaluators: dict[ReconciliationRuleType, ReconciliationEvaluator] = {
            ReconciliationRuleType.ROW_EQUATION: RowEquationEvaluator(),
            ReconciliationRuleType.AGGREGATE_EQUATION: AggregateEquationEvaluator(),
            ReconciliationRuleType.GROUPED_AGGREGATE: GroupedAggregateEvaluator(),
        }

    def reconcile(
        self, dataset: CanonicalDataset, rule_set: ReconciliationRuleSet
    ) -> ReconciliationReport:
        structural_result = self._structural_validator.validate(dataset)
        if not structural_result.valid:
            raise DatasetNotStructurallyValidError(structural_result)
        self.validate_configuration(dataset, rule_set)

        summaries: list[ReconciliationRuleSummary] = []
        findings: list[ReconciliationFinding] = []
        for rule in rule_set.rules:
            evaluations = self._evaluators[rule.type].evaluate(rule, dataset)
            findings.extend(
                item.finding for item in evaluations if item.finding is not None
            )
            summaries.append(self._summarise(rule, evaluations))

        blocking = sum(item.severity == RuleSeverity.BLOCKING for item in findings)
        review = sum(item.severity == RuleSeverity.REVIEW for item in findings)
        report_summary = ReconciliationReportSummary(
            rules=len(rule_set.rules),
            blocking_findings=blocking,
            review_findings=review,
            passed_checks=sum(item.passed_count for item in summaries),
            skipped_checks=sum(item.skipped_count for item in summaries),
        )
        data_fingerprint = dataset_fingerprint(dataset)
        fingerprint = self._fingerprint(
            data_fingerprint, rule_set, tuple(summaries), tuple(findings)
        )
        report = ReconciliationReport(
            dataset_id=dataset.dataset_id,
            dataset_fingerprint=data_fingerprint,
            rule_set_id=rule_set.id,
            rule_set_version=rule_set.version,
            valid=True,
            ready=blocking == 0,
            summary=report_summary,
            rule_summaries=tuple(summaries),
            findings=tuple(findings),
            evaluated_at=datetime.now(UTC),
            fingerprint=fingerprint,
        )
        logger.info(
            "Reconciliation complete: dataset=%s rules=%d blocking=%d review=%d",
            dataset.dataset_id,
            len(rule_set.rules),
            blocking,
            review,
        )
        return report

    @staticmethod
    def _summarise(
        rule: ReconciliationRule, evaluations: list[ReconciliationEvaluation]
    ) -> ReconciliationRuleSummary:
        passed = sum(item.outcome == RuleOutcome.PASSED for item in evaluations)
        failed = sum(item.outcome == RuleOutcome.FAILED for item in evaluations)
        skipped = sum(item.outcome == RuleOutcome.SKIPPED for item in evaluations)
        return ReconciliationRuleSummary(
            rule_id=rule.id,
            rule_type=rule.type,
            severity=rule.severity,
            evaluated_count=passed + failed,
            passed_count=passed,
            failed_count=failed,
            skipped_count=skipped,
        )

    @staticmethod
    def validate_configuration(
        dataset: CanonicalDataset, rule_set: ReconciliationRuleSet
    ) -> None:
        fields = dataset.canonical_schema.fields_by_id
        numeric = {CanonicalDataType.INTEGER, CanonicalDataType.DECIMAL}

        def require_field(field_id: str, rule_id: str) -> CanonicalDataType:
            field = fields.get(field_id)
            if field is None:
                raise ReconciliationRuleSetConfigurationError(
                    f"Rule '{rule_id}' references an unknown canonical field."
                )
            return field.data_type

        def require_numeric(field_id: str, rule_id: str) -> None:
            if require_field(field_id, rule_id) not in numeric:
                raise ReconciliationRuleSetConfigurationError(
                    f"Rule '{rule_id}' requires numeric canonical fields."
                )

        def validate_aggregate(aggregate, rule_id: str) -> None:
            data_type = require_field(aggregate.field_id, rule_id)
            if aggregate.aggregate == AggregateFunction.SUM and data_type not in numeric:
                raise ReconciliationRuleSetConfigurationError(
                    f"Rule '{rule_id}' sum aggregate requires a numeric field."
                )

        for rule in rule_set.rules:
            if isinstance(rule, RowEquationRule):
                for term in rule.left:
                    require_numeric(term.field_id, rule.id)
                require_numeric(rule.right.field_id, rule.id)
            elif isinstance(rule, (AggregateEquationRule, GroupedAggregateRule)):
                for term in rule.left:
                    validate_aggregate(term, rule.id)
                validate_aggregate(rule.right, rule.id)
                if isinstance(rule, GroupedAggregateRule):
                    for field_id in rule.group_by:
                        require_field(field_id, rule.id)

    @staticmethod
    def _fingerprint(
        data_fingerprint: str,
        rule_set: ReconciliationRuleSet,
        summaries: tuple[ReconciliationRuleSummary, ...],
        findings: tuple[ReconciliationFinding, ...],
    ) -> str:
        content = {
            "dataset_fingerprint": data_fingerprint,
            "rule_set": rule_set.model_dump(mode="json"),
            "rule_summaries": [item.model_dump(mode="json") for item in summaries],
            "findings": [item.model_dump(mode="json") for item in findings],
        }
        encoded = json.dumps(
            content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
