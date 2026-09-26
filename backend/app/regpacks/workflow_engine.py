from __future__ import annotations

import hashlib
import json
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.canonical.fingerprint import dataset_fingerprint
from app.canonical.models import CanonicalDataset
from app.reconciliation.engine import ReconciliationEngine
from app.reconciliation.models import ReconciliationReport
from app.regpacks.errors import RegPackComponentError
from app.regpacks.models import LoadedRegPack
from app.regpacks.workflow import (
    DateOrderWorkflowRule,
    RecordDateRangeWorkflowRule,
    RuntimeFieldIssue,
    RuntimeValidationResult,
    parse_runtime_value,
)
from app.validation.engine import ValidationEngine
from app.validation.models import RuleSeverity, ValidationReport


class WorkflowRunModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WorkflowSectionRunResult(WorkflowRunModel):
    section_id: str
    dataset_fingerprint: str
    record_count: int
    validation_report: ValidationReport
    reconciliation_status: str
    reconciliation_report: ReconciliationReport | None = None
    ready: bool


class WorkflowRunResult(WorkflowRunModel):
    pack_id: str
    pack_version: str
    pack_fingerprint: str
    bundle_id: str
    bundle_fingerprint: str
    runtime_validation: RuntimeValidationResult
    runtime_values: dict[str, object]
    sections: tuple[WorkflowSectionRunResult, ...]
    ready: bool
    validation_fingerprint: str
    reconciliation_fingerprint: str


class WorkflowRunner:
    def __init__(self) -> None:
        self.validation_engine = ValidationEngine()
        self.reconciliation_engine = ReconciliationEngine()

    def run(
        self,
        pack: LoadedRegPack,
        datasets: dict[str, CanonicalDataset],
        runtime_values: dict[str, object],
        *,
        bundle_id: str,
    ) -> WorkflowRunResult:
        workflow = pack.workflow_definition
        if workflow is None or not pack.sections or pack.fingerprint is None:
            raise RegPackComponentError("The RegPack has no executable workflow definition.")
        expected = {section.id for section in pack.sections}
        if set(datasets) != expected:
            raise RegPackComponentError("The canonical dataset bundle does not match the workflow sections.")
        parsed_runtime, runtime_result = self._validate_runtime(pack, datasets, runtime_values)
        section_results: list[WorkflowSectionRunResult] = []
        for section in pack.sections:
            dataset = datasets[section.id]
            if (
                dataset.canonical_schema.id != section.canonical_schema.id
                or dataset.canonical_schema.version != section.canonical_schema.version
            ):
                raise RegPackComponentError("A canonical section schema does not match the RegPack.")
            validation = self.validation_engine.validate(dataset, section.validation_rules)
            reconciliation = (
                self.reconciliation_engine.reconcile(dataset, section.reconciliation_rules)
                if section.reconciliation_rules is not None
                else None
            )
            ready = validation.ready and (reconciliation is None or reconciliation.ready)
            section_results.append(
                WorkflowSectionRunResult(
                    section_id=section.id,
                    dataset_fingerprint=dataset_fingerprint(dataset),
                    record_count=len(dataset.records),
                    validation_report=validation,
                    reconciliation_status=("applicable" if reconciliation is not None else "not_applicable"),
                    reconciliation_report=reconciliation,
                    ready=ready,
                )
            )
        bundle_fingerprint = self.bundle_fingerprint(datasets)
        validation_fingerprint = _fingerprint({
            "runtime": runtime_result.fingerprint,
            "sections": {
                item.section_id: item.validation_report.report_fingerprint
                for item in section_results
            },
        })
        reconciliation_fingerprint = _fingerprint({
            item.section_id: (
                item.reconciliation_report.fingerprint
                if item.reconciliation_report is not None
                else "not_applicable"
            )
            for item in section_results
        })
        return WorkflowRunResult(
            pack_id=pack.id,
            pack_version=pack.version,
            pack_fingerprint=pack.fingerprint,
            bundle_id=bundle_id,
            bundle_fingerprint=bundle_fingerprint,
            runtime_validation=runtime_result,
            runtime_values=parsed_runtime,
            sections=tuple(section_results),
            ready=runtime_result.ready and all(item.ready for item in section_results),
            validation_fingerprint=validation_fingerprint,
            reconciliation_fingerprint=reconciliation_fingerprint,
        )

    def _validate_runtime(
        self,
        pack: LoadedRegPack,
        datasets: dict[str, CanonicalDataset],
        supplied: dict[str, object],
    ) -> tuple[dict[str, object], RuntimeValidationResult]:
        workflow = pack.workflow_definition
        assert workflow is not None
        definitions = {field.id: field for field in workflow.runtime_fields}
        if not set(supplied).issubset(definitions):
            raise RegPackComponentError("Runtime values contain an unknown field.")
        parsed: dict[str, object] = {}
        findings: list[RuntimeFieldIssue] = []
        passed = 0
        for field in workflow.runtime_fields:
            value = supplied.get(field.id)
            if value is None or value == "":
                if field.required:
                    findings.append(RuntimeFieldIssue(
                        rule_id=f"RUNTIME-{field.id.upper().replace('_', '-')}-REQUIRED",
                        severity=RuleSeverity.BLOCKING,
                        message=f"{field.name} is required.",
                        field_id=field.id,
                        source_refs=field.source_refs,
                    ))
                continue
            try:
                parsed_value = parse_runtime_value(field, value)
            except (ValueError, TypeError):
                findings.append(RuntimeFieldIssue(
                    rule_id=f"RUNTIME-{field.id.upper().replace('_', '-')}-TYPE",
                    severity=RuleSeverity.BLOCKING,
                    message=f"{field.name} has an invalid value type.",
                    field_id=field.id,
                    source_refs=field.source_refs,
                ))
                continue
            if field.max_length is not None and len(str(parsed_value)) > field.max_length:
                findings.append(RuntimeFieldIssue(
                    rule_id=f"RUNTIME-{field.id.upper().replace('_', '-')}-LENGTH",
                    severity=RuleSeverity.BLOCKING,
                    message=f"{field.name} exceeds {field.max_length} characters.",
                    field_id=field.id,
                    source_refs=field.source_refs,
                ))
                continue
            parsed[field.id] = parsed_value
            passed += 1
        for rule in workflow.rules:
            start = parsed.get(rule.start_field_id)
            end = parsed.get(rule.end_field_id)
            if not isinstance(start, date) or not isinstance(end, date):
                continue
            if isinstance(rule, DateOrderWorkflowRule):
                if end < start:
                    findings.append(RuntimeFieldIssue(
                        rule_id=rule.id,
                        severity=rule.severity,
                        message=rule.description,
                        field_id=rule.end_field_id,
                        source_refs=rule.source_refs,
                    ))
                else:
                    passed += 1
            elif isinstance(rule, RecordDateRangeWorkflowRule):
                for record in datasets[rule.section_id].records:
                    canonical = record.values.get(rule.field_id)
                    value = canonical.value if canonical is not None else None
                    if value is None:
                        continue
                    if not isinstance(value, date) or value < start or value > end:
                        findings.append(RuntimeFieldIssue(
                            rule_id=rule.id,
                            severity=rule.severity,
                            message=rule.description,
                            field_id=rule.field_id,
                            section_id=rule.section_id,
                            record_id=record.record_id,
                            source_refs=rule.source_refs,
                        ))
                    else:
                        passed += 1
        blocking = sum(item.severity == RuleSeverity.BLOCKING for item in findings)
        review = sum(item.severity == RuleSeverity.REVIEW for item in findings)
        fingerprint = _fingerprint({
            "definitions": [field.model_dump(mode="json") for field in workflow.runtime_fields],
            "rules": [rule.model_dump(mode="json") for rule in workflow.rules],
            "outcomes": [item.model_dump(mode="json") for item in findings],
            "presence": sorted(parsed),
        })
        return parsed, RuntimeValidationResult(
            valid=True,
            ready=blocking == 0,
            blocking_findings=blocking,
            review_findings=review,
            passed_checks=passed,
            findings=tuple(findings),
            fingerprint=fingerprint,
        )

    @staticmethod
    def bundle_fingerprint(datasets: dict[str, CanonicalDataset]) -> str:
        return _fingerprint({
            section_id: dataset_fingerprint(dataset)
            for section_id, dataset in sorted(datasets.items())
        })


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
