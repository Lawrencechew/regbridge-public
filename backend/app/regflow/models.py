from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.imports.models import ImportIssue, ImportedDatasetSummary, SourceType
from app.reconciliation.models import ReconciliationFinding
from app.validation.models import ValidationFinding
from app.regpacks.workflow import RuntimeFieldIssue


class RegFlowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RegFlowSourceEvidence(RegFlowModel):
    id: str
    title: str
    publisher: str
    url: str
    reference: str | None = None


class RegFlowPackSummary(RegFlowModel):
    id: str
    version: str
    name: str
    regulator_code: str
    regulator_name: str
    status: str | None
    fingerprint: str
    output_configured: bool
    sources: tuple[RegFlowSourceEvidence, ...]


class RegFlowSourceSummary(RegFlowModel):
    source_name: str
    source_type: SourceType
    file_size_bytes: int = Field(ge=0)
    file_sha256: str
    selected_sheet: str | None
    data_row_count: int | None = Field(default=None, ge=0)
    column_count: int = Field(ge=0)
    formula_cells_detected: bool
    warnings: tuple[str, ...]
    source_header_signature: str
    source_signature_version: str


class RegFlowValidationResult(RegFlowModel):
    rule_set_id: str
    rule_set_version: str
    valid: bool
    ready: bool
    blocking_findings: int = Field(ge=0)
    review_findings: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    skipped_checks: int = Field(ge=0)
    total_findings: int = Field(ge=0)
    returned_findings: int = Field(ge=0)
    findings_truncated: bool
    findings: tuple[ValidationFinding, ...]
    report_fingerprint: str


class RegFlowReconciliationResult(RegFlowModel):
    rule_set_id: str
    rule_set_version: str
    valid: bool
    ready: bool
    blocking_findings: int = Field(ge=0)
    review_findings: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    skipped_checks: int = Field(ge=0)
    total_findings: int = Field(ge=0)
    returned_findings: int = Field(ge=0)
    findings_truncated: bool
    findings: tuple[ReconciliationFinding, ...]
    report_fingerprint: str


class RegFlowPreflightResult(RegFlowModel):
    success: bool
    pack: RegFlowPackSummary
    source_summary: RegFlowSourceSummary
    mapping_fingerprint: str
    dataset_summary: ImportedDatasetSummary | None = None
    dataset_fingerprint: str | None = None
    import_issues: tuple[ImportIssue, ...] = ()
    total_import_issues: int = Field(default=0, ge=0)
    returned_import_issues: int = Field(default=0, ge=0)
    import_issues_truncated: bool = False
    validation: RegFlowValidationResult | None = None
    reconciliation: RegFlowReconciliationResult | None = None
    blocking_findings: int = Field(default=0, ge=0)
    review_findings: int = Field(default=0, ge=0)
    passed_checks: int = Field(default=0, ge=0)
    ready: bool
    can_generate: bool
    run_id: str | None = None
    run_state: str | None = None
    run_revision: int | None = None


class RegFlowRuntimeValidationResult(RegFlowModel):
    valid: bool
    ready: bool
    blocking_findings: int = Field(ge=0)
    review_findings: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    findings: tuple[RuntimeFieldIssue, ...]
    fingerprint: str


class RegFlowSectionPreflightResult(RegFlowModel):
    section_id: str
    success: bool
    omitted: bool
    source_summary: RegFlowSourceSummary | None = None
    mapping_fingerprint: str | None = None
    dataset_summary: ImportedDatasetSummary
    dataset_fingerprint: str | None = None
    import_issues: tuple[ImportIssue, ...] = ()
    validation: RegFlowValidationResult | None = None
    reconciliation_status: str = "not_applicable"
    reconciliation: RegFlowReconciliationResult | None = None
    ready: bool


class RegFlowWorkflowPreflightResult(RegFlowModel):
    success: bool
    pack: RegFlowPackSummary
    mapping_fingerprint: str
    bundle_id: str | None = None
    bundle_fingerprint: str | None = None
    runtime_validation: RegFlowRuntimeValidationResult | None = None
    sections: tuple[RegFlowSectionPreflightResult, ...]
    blocking_findings: int = Field(ge=0)
    review_findings: int = Field(ge=0)
    passed_checks: int = Field(ge=0)
    ready: bool
    can_generate: bool
    validation_fingerprint: str | None = None
    reconciliation_fingerprint: str | None = None
    run_id: str | None = None
    run_state: str | None = None
    run_revision: int | None = None
