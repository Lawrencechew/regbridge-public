from __future__ import annotations

import logging
from time import monotonic
from uuid import uuid4

from app.imports.models import ImportMapping, SourceFileInspection, WorkflowImportMapping
from app.imports.service import ImportService
from app.regflow.models import (
    RegFlowPackSummary,
    RegFlowPreflightResult,
    RegFlowReconciliationResult,
    RegFlowSourceEvidence,
    RegFlowSourceSummary,
    RegFlowValidationResult,
    RegFlowRuntimeValidationResult,
    RegFlowSectionPreflightResult,
    RegFlowWorkflowPreflightResult,
)
from app.regpacks.models import LoadedRegPack
from app.regpacks.runner import RegPackRunner
from app.regpacks.workflow_engine import WorkflowRunner

logger = logging.getLogger(__name__)


class RegFlowPreflightService:
    def __init__(
        self,
        import_service: ImportService,
        runner: RegPackRunner,
        max_findings: int,
    ) -> None:
        self.import_service = import_service
        self.runner = runner
        self.max_findings = max_findings
        self.workflow_runner = WorkflowRunner()

    def run(
        self,
        pack: LoadedRegPack,
        source_name: str,
        content: bytes,
        mapping: ImportMapping,
    ) -> RegFlowPreflightResult:
        started = monotonic()
        imported = self.import_service.map(
            source_name, content, mapping, pack.canonical_schema
        )
        pack_summary = self._pack_summary(pack)
        source_summary = self._source_summary(imported.source)
        if not imported.success or imported.dataset is None:
            issues = imported.issues[: self.max_findings]
            result = RegFlowPreflightResult(
                success=False,
                pack=pack_summary,
                source_summary=source_summary,
                mapping_fingerprint=imported.mapping_fingerprint,
                import_issues=issues,
                total_import_issues=len(imported.issues),
                returned_import_issues=len(issues),
                import_issues_truncated=len(issues) < len(imported.issues),
                ready=False,
                can_generate=False,
            )
            self._log(pack, 0, len(imported.issues), 0, started)
            return result

        run = self.runner.run(pack, imported.dataset)
        validation_findings = run.validation_report.findings[: self.max_findings]
        remaining = max(self.max_findings - len(validation_findings), 0)
        reconciliation_findings = run.reconciliation_report.findings[:remaining]
        validation = RegFlowValidationResult(
            rule_set_id=run.validation_report.rule_set_id,
            rule_set_version=run.validation_report.rule_set_version,
            valid=run.validation_report.valid,
            ready=run.validation_report.ready,
            blocking_findings=run.validation_report.summary.blocking_findings,
            review_findings=run.validation_report.summary.review_findings,
            passed_checks=run.validation_report.summary.passed_checks,
            skipped_checks=run.validation_report.summary.skipped_checks,
            total_findings=len(run.validation_report.findings),
            returned_findings=len(validation_findings),
            findings_truncated=len(validation_findings) < len(run.validation_report.findings),
            findings=validation_findings,
            report_fingerprint=run.validation_report.report_fingerprint,
        )
        reconciliation = RegFlowReconciliationResult(
            rule_set_id=run.reconciliation_report.rule_set_id,
            rule_set_version=run.reconciliation_report.rule_set_version,
            valid=run.reconciliation_report.valid,
            ready=run.reconciliation_report.ready,
            blocking_findings=run.reconciliation_report.summary.blocking_findings,
            review_findings=run.reconciliation_report.summary.review_findings,
            passed_checks=run.reconciliation_report.summary.passed_checks,
            skipped_checks=run.reconciliation_report.summary.skipped_checks,
            total_findings=len(run.reconciliation_report.findings),
            returned_findings=len(reconciliation_findings),
            findings_truncated=(
                len(reconciliation_findings) < len(run.reconciliation_report.findings)
            ),
            findings=reconciliation_findings,
            report_fingerprint=run.reconciliation_report.fingerprint,
        )
        blocking = validation.blocking_findings + reconciliation.blocking_findings
        review = validation.review_findings + reconciliation.review_findings
        passed = validation.passed_checks + reconciliation.passed_checks
        ready = validation.ready and reconciliation.ready
        result = RegFlowPreflightResult(
            success=True,
            pack=pack_summary,
            source_summary=source_summary,
            mapping_fingerprint=imported.mapping_fingerprint,
            dataset_summary=imported.dataset_summary,
            dataset_fingerprint=run.dataset_fingerprint,
            validation=validation,
            reconciliation=reconciliation,
            blocking_findings=blocking,
            review_findings=review,
            passed_checks=passed,
            ready=ready,
            can_generate=ready and pack.output_definition is not None,
        )
        self._log(pack, len(imported.dataset.records), blocking, review, started)
        return result

    def run_workflow(
        self,
        pack: LoadedRegPack,
        source_name: str,
        content: bytes,
        mapping: WorkflowImportMapping,
        runtime_values: dict[str, object],
    ) -> RegFlowWorkflowPreflightResult:
        started = monotonic()
        imported = self.import_service.map_workflow(
            source_name, content, mapping, pack
        )
        pack_summary = self._pack_summary(pack)
        if not imported.success:
            sections = tuple(
                RegFlowSectionPreflightResult(
                    section_id=item.section_id,
                    success=item.success,
                    omitted=item.omitted,
                    source_summary=(self._source_summary(item.source) if item.source else None),
                    mapping_fingerprint=item.mapping_fingerprint,
                    dataset_summary=item.dataset_summary,
                    import_issues=item.issues[: self.max_findings],
                    ready=False,
                )
                for item in imported.sections
            )
            blocking = sum(len(item.import_issues) for item in sections)
            self._log(pack, 0, blocking, 0, started)
            return RegFlowWorkflowPreflightResult(
                success=False,
                pack=pack_summary,
                mapping_fingerprint=imported.mapping_fingerprint,
                sections=sections,
                blocking_findings=blocking,
                ready=False,
                can_generate=False,
            )
        bundle_id = f"workflow-{uuid4()}"
        run = self.workflow_runner.run(
            pack,
            imported.datasets,
            runtime_values,
            bundle_id=bundle_id,
        )
        imported_by_id = {item.section_id: item for item in imported.sections}
        section_results: list[RegFlowSectionPreflightResult] = []
        for section_run in run.sections:
            item = imported_by_id[section_run.section_id]
            validation = self._validation_result(section_run.validation_report)
            reconciliation = (
                self._reconciliation_result(section_run.reconciliation_report)
                if section_run.reconciliation_report is not None
                else None
            )
            section_results.append(RegFlowSectionPreflightResult(
                section_id=item.section_id,
                success=True,
                omitted=item.omitted,
                source_summary=(self._source_summary(item.source) if item.source else None),
                mapping_fingerprint=item.mapping_fingerprint,
                dataset_summary=item.dataset_summary,
                dataset_fingerprint=section_run.dataset_fingerprint,
                validation=validation,
                reconciliation_status=section_run.reconciliation_status,
                reconciliation=reconciliation,
                ready=section_run.ready,
            ))
        runtime = RegFlowRuntimeValidationResult.model_validate(
            run.runtime_validation.model_dump(mode="python")
        )
        blocking = runtime.blocking_findings + sum(
            item.validation.blocking_findings
            + (item.reconciliation.blocking_findings if item.reconciliation else 0)
            for item in section_results
            if item.validation is not None
        )
        review = runtime.review_findings + sum(
            item.validation.review_findings
            + (item.reconciliation.review_findings if item.reconciliation else 0)
            for item in section_results
            if item.validation is not None
        )
        passed = runtime.passed_checks + sum(
            item.validation.passed_checks
            + (item.reconciliation.passed_checks if item.reconciliation else 0)
            for item in section_results
            if item.validation is not None
        )
        self._log(
            pack,
            sum(item.dataset_summary.record_count for item in imported.sections),
            blocking,
            review,
            started,
        )
        return RegFlowWorkflowPreflightResult(
            success=True,
            pack=pack_summary,
            mapping_fingerprint=imported.mapping_fingerprint,
            bundle_id=bundle_id,
            bundle_fingerprint=run.bundle_fingerprint,
            runtime_validation=runtime,
            sections=tuple(section_results),
            blocking_findings=blocking,
            review_findings=review,
            passed_checks=passed,
            ready=run.ready,
            can_generate=run.ready and pack.output_definition is not None,
            validation_fingerprint=run.validation_fingerprint,
            reconciliation_fingerprint=run.reconciliation_fingerprint,
        )

    def _validation_result(self, report):
        findings = report.findings[: self.max_findings]
        return RegFlowValidationResult(
            rule_set_id=report.rule_set_id,
            rule_set_version=report.rule_set_version,
            valid=report.valid,
            ready=report.ready,
            blocking_findings=report.summary.blocking_findings,
            review_findings=report.summary.review_findings,
            passed_checks=report.summary.passed_checks,
            skipped_checks=report.summary.skipped_checks,
            total_findings=len(report.findings),
            returned_findings=len(findings),
            findings_truncated=len(findings) < len(report.findings),
            findings=findings,
            report_fingerprint=report.report_fingerprint,
        )

    def _reconciliation_result(self, report):
        findings = report.findings[: self.max_findings]
        return RegFlowReconciliationResult(
            rule_set_id=report.rule_set_id,
            rule_set_version=report.rule_set_version,
            valid=report.valid,
            ready=report.ready,
            blocking_findings=report.summary.blocking_findings,
            review_findings=report.summary.review_findings,
            passed_checks=report.summary.passed_checks,
            skipped_checks=report.summary.skipped_checks,
            total_findings=len(report.findings),
            returned_findings=len(findings),
            findings_truncated=len(findings) < len(report.findings),
            findings=findings,
            report_fingerprint=report.fingerprint,
        )

    @staticmethod
    def _pack_summary(pack: LoadedRegPack) -> RegFlowPackSummary:
        return RegFlowPackSummary(
            id=pack.id,
            version=pack.version,
            name=pack.name,
            regulator_code=pack.regulator.code,
            regulator_name=pack.regulator.name,
            status=pack.manifest.status,
            fingerprint=pack.fingerprint,
            output_configured=pack.output_definition is not None,
            sources=tuple(
                RegFlowSourceEvidence(
                    id=source.id,
                    title=source.title,
                    publisher=source.publisher,
                    url=str(source.url),
                    reference=source.reference,
                )
                for source in pack.manifest.sources
            ),
        )

    @staticmethod
    def _source_summary(inspection: SourceFileInspection) -> RegFlowSourceSummary:
        return RegFlowSourceSummary(
            source_name=inspection.source_name,
            source_type=inspection.source_type,
            file_size_bytes=inspection.file_size_bytes,
            file_sha256=inspection.file_sha256,
            selected_sheet=inspection.selected_sheet,
            data_row_count=inspection.data_row_count,
            column_count=len(inspection.columns),
            formula_cells_detected=inspection.formula_cells_detected,
            warnings=inspection.warnings,
            source_header_signature=inspection.source_header_signature,
            source_signature_version=inspection.source_signature_version,
        )

    @staticmethod
    def _log(pack, records: int, blocking: int, review: int, started: float) -> None:
        logger.info(
            "RegFlow preflight complete: pack=%s version=%s records=%d blocking=%d review=%d duration_ms=%d",
            pack.id,
            pack.version,
            records,
            blocking,
            review,
            int((monotonic() - started) * 1000),
        )
