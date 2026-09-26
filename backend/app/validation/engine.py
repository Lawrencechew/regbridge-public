import hashlib
import json
import logging
from datetime import UTC, datetime

from app.canonical.fingerprint import dataset_fingerprint
from app.canonical.models import (
    CanonicalDataType,
    CanonicalDataset,
    canonical_value_matches_type,
)
from app.canonical.validation import CanonicalStructuralValidator
from app.validation.errors import (
    DatasetNotStructurallyValidError,
    RuleSetConfigurationError,
)
from app.validation.evaluators import (
    AllowedCharactersEvaluator,
    ConditionalRequiredEvaluator,
    DecimalPlacesEvaluator,
    EnumEvaluator,
    Evaluation,
    MaximumEvaluator,
    MinimumEvaluator,
    NotBlankEvaluator,
    RegexEvaluator,
    RequiredEvaluator,
    RuleEvaluator,
    UniqueEvaluator,
)
from app.validation.models import (
    ConditionalRequiredRule,
    DecimalPlacesRule,
    EnumRule,
    MaximumRule,
    MinimumRule,
    RuleOutcome,
    RuleSet,
    RuleSeverity,
    RuleType,
    ValidationFinding,
    ValidationReport,
    ValidationReportSummary,
    ValidationRule,
    ValidationRuleSummary,
)

logger = logging.getLogger(__name__)


class ValidationEngine:
    def __init__(self) -> None:
        self._structural_validator = CanonicalStructuralValidator()
        self._evaluators: dict[RuleType, RuleEvaluator] = {
            RuleType.REQUIRED: RequiredEvaluator(),
            RuleType.NOT_BLANK: NotBlankEvaluator(),
            RuleType.ENUM: EnumEvaluator(),
            RuleType.MINIMUM: MinimumEvaluator(),
            RuleType.MAXIMUM: MaximumEvaluator(),
            RuleType.DECIMAL_PLACES: DecimalPlacesEvaluator(),
            RuleType.REGEX: RegexEvaluator(),
            RuleType.ALLOWED_CHARACTERS: AllowedCharactersEvaluator(),
            RuleType.UNIQUE: UniqueEvaluator(),
            RuleType.CONDITIONAL_REQUIRED: ConditionalRequiredEvaluator(),
        }

    def validate(self, dataset: CanonicalDataset, rule_set: RuleSet) -> ValidationReport:
        structural_result = self._structural_validator.validate(dataset)
        if not structural_result.valid:
            raise DatasetNotStructurallyValidError(structural_result)

        self.validate_configuration(dataset, rule_set)
        rule_summaries: list[ValidationRuleSummary] = []
        findings: list[ValidationFinding] = []

        for rule in rule_set.rules:
            evaluations = self._evaluators[rule.type].evaluate(rule, dataset)
            findings.extend(
                evaluation.finding
                for evaluation in evaluations
                if evaluation.finding is not None
            )
            rule_summaries.append(self._summarise_rule(rule, evaluations))

        blocking_findings = sum(
            finding.severity == RuleSeverity.BLOCKING for finding in findings
        )
        review_findings = sum(
            finding.severity == RuleSeverity.REVIEW for finding in findings
        )
        report_summary = ValidationReportSummary(
            rules=len(rule_set.rules),
            blocking_findings=blocking_findings,
            review_findings=review_findings,
            passed_checks=sum(summary.passed_count for summary in rule_summaries),
            skipped_checks=sum(summary.skipped_count for summary in rule_summaries),
        )
        data_fingerprint = dataset_fingerprint(dataset)
        report_fingerprint = self._report_fingerprint(
            data_fingerprint, rule_set, tuple(rule_summaries), tuple(findings)
        )
        report = ValidationReport(
            dataset_id=dataset.dataset_id,
            dataset_fingerprint=data_fingerprint,
            rule_set_id=rule_set.id,
            rule_set_version=rule_set.version,
            valid=True,
            ready=blocking_findings == 0,
            summary=report_summary,
            rule_summaries=tuple(rule_summaries),
            findings=tuple(findings),
            report_fingerprint=report_fingerprint,
            evaluated_at=datetime.now(UTC),
        )
        logger.info(
            "Validation completed: dataset=%s rules=%d blocking=%d review=%d",
            dataset.dataset_id,
            len(rule_set.rules),
            blocking_findings,
            review_findings,
        )
        return report

    @staticmethod
    def _summarise_rule(
        rule: ValidationRule, evaluations: list[Evaluation]
    ) -> ValidationRuleSummary:
        passed = sum(item.outcome == RuleOutcome.PASSED for item in evaluations)
        failed = sum(item.outcome == RuleOutcome.FAILED for item in evaluations)
        skipped = sum(item.outcome == RuleOutcome.SKIPPED for item in evaluations)
        return ValidationRuleSummary(
            rule_id=rule.id,
            rule_type=rule.type,
            severity=rule.severity,
            evaluated_count=passed + failed,
            passed_count=passed,
            failed_count=failed,
            skipped_count=skipped,
        )

    @staticmethod
    def validate_configuration(dataset: CanonicalDataset, rule_set: RuleSet) -> None:
        fields = dataset.canonical_schema.fields_by_id
        comparable_types = {
            CanonicalDataType.INTEGER,
            CanonicalDataType.DECIMAL,
            CanonicalDataType.DATE,
            CanonicalDataType.DATETIME,
        }
        string_rule_types = {RuleType.REGEX, RuleType.ALLOWED_CHARACTERS}

        for rule in rule_set.rules:
            field = fields.get(rule.field_id)
            if field is None:
                raise RuleSetConfigurationError(
                    f"Rule '{rule.id}' references an unknown canonical field."
                )
            if rule.type in string_rule_types and field.data_type != CanonicalDataType.STRING:
                raise RuleSetConfigurationError(
                    f"Rule '{rule.id}' requires a canonical string field."
                )
            if isinstance(rule, DecimalPlacesRule) and field.data_type != CanonicalDataType.DECIMAL:
                raise RuleSetConfigurationError(
                    f"Rule '{rule.id}' requires a canonical decimal field."
                )
            if isinstance(rule, (MinimumRule, MaximumRule)):
                if field.data_type not in comparable_types:
                    raise RuleSetConfigurationError(
                        f"Rule '{rule.id}' targets a non-orderable canonical field."
                    )
                boundary = rule.minimum if isinstance(rule, MinimumRule) else rule.maximum
                if not canonical_value_matches_type(boundary, field.data_type):
                    raise RuleSetConfigurationError(
                        f"Rule '{rule.id}' boundary is incompatible with its field type."
                    )
            if isinstance(rule, EnumRule) and any(
                not canonical_value_matches_type(value, field.data_type)
                for value in rule.allowed_values
            ):
                raise RuleSetConfigurationError(
                    f"Rule '{rule.id}' allowed values are incompatible with its field type."
                )
            if isinstance(rule, ConditionalRequiredRule):
                condition_field = fields.get(rule.when.field_id)
                if condition_field is None:
                    raise RuleSetConfigurationError(
                        f"Rule '{rule.id}' condition references an unknown canonical field."
                    )
                if rule.when.value is not None and not canonical_value_matches_type(
                    rule.when.value, condition_field.data_type
                ):
                    raise RuleSetConfigurationError(
                        f"Rule '{rule.id}' condition value is incompatible with its field type."
                    )

    @staticmethod
    def _report_fingerprint(
        data_fingerprint: str,
        rule_set: RuleSet,
        summaries: tuple[ValidationRuleSummary, ...],
        findings: tuple[ValidationFinding, ...],
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
