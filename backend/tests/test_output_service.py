from datetime import date
from decimal import Decimal

from app.canonical.models import CanonicalDataset
from app.outputs.models import OutputIssueCode
from app.outputs.service import OutputService
from app.reconciliation.models import FieldOperand, FieldTerm, ReconciliationRuleSet, RowEquationRule
from app.regpacks.models import EffectivePeriod, LoadedRegPack, RegPackManifest, RegulatorySource, RegulatorMetadata
from app.validation.models import NotBlankRule, RuleSet, RuleSeverity
from tests.output_helpers import output_dataset, output_definition, output_schema, write_output_template


def loaded_pack(tmp_path, *, validation_severity=RuleSeverity.BLOCKING, reconciliation_severity=RuleSeverity.BLOCKING, configured=True):
    template = tmp_path / "template.xlsx"
    digest = write_output_template(template)
    schema = output_schema()
    manifest = RegPackManifest(
        schema_version="1.0",
        id="synthetic-output-pack",
        name="Synthetic output pack",
        regulator=RegulatorMetadata(code="SYN", name="Synthetic"),
        version="1.0.0",
        effective=EffectivePeriod(from_date=date(2026, 1, 1)),
        description="Synthetic output test pack",
        sources=[RegulatorySource(id="SRC-001", title="Source", publisher="Synthetic", url="https://example.com", checked_at=date(2026, 1, 1))],
    )
    validation = RuleSet(
        id="SYN-VALIDATION", version="1.0.0", name="Validation",
        rules=(NotBlankRule(id="SYN-VAL-1", name="Name", description="Name required", severity=validation_severity, field_id="name"),),
    )
    reconciliation = ReconciliationRuleSet(
        id="SYN-RECONCILIATION", version="1.0.0", name="Reconciliation",
        rules=(RowEquationRule(id="SYN-REC-1", name="Amounts", description="Amounts balance", severity=reconciliation_severity, left=(FieldTerm(field_id="amount"),), right=FieldOperand(field_id="expected_amount")),),
    )
    return LoadedRegPack(
        manifest=manifest,
        canonical_schema=schema,
        validation_rules=validation,
        reconciliation_rules=reconciliation,
        output_definition=output_definition(template, digest) if configured else None,
        output_template_path=template if configured else None,
        fingerprint="a" * 64,
    )


def test_all_preconditions_pass_and_artifact_metadata_is_complete(tmp_path) -> None:
    generated = OutputService(1024 * 1024).generate(loaded_pack(tmp_path), output_dataset())
    assert generated.result.success and generated.content
    artifact = generated.result.artifact
    assert artifact.media_type.endswith("spreadsheetml.sheet")
    assert artifact.size_bytes == len(generated.content)
    assert len(artifact.sha256) == 64
    assert artifact.output_definition_version == "1.0.0"


def test_output_not_configured_and_schema_mismatch(tmp_path) -> None:
    result = OutputService(1024 * 1024).generate(loaded_pack(tmp_path, configured=False), output_dataset()).result
    assert result.issues[0].code == OutputIssueCode.OUTPUT_NOT_CONFIGURED
    dataset = output_dataset().model_copy(update={"canonical_schema": output_schema().model_copy(update={"version": "2.0.0"})})
    result = OutputService(1024 * 1024).generate(loaded_pack(tmp_path), dataset).result
    assert result.issues[0].code == OutputIssueCode.OUTPUT_SCHEMA_MISMATCH


def test_structurally_invalid_dataset_is_blocked(tmp_path) -> None:
    dataset = output_dataset()
    dataset = dataset.model_copy(update={"records": [dataset.records[0], dataset.records[0]]})
    result = OutputService(1024 * 1024).generate(loaded_pack(tmp_path), dataset).result
    assert result.issues[0].code == OutputIssueCode.OUTPUT_STRUCTURAL_VALIDATION_FAILED


def test_blocking_validation_is_blocked_but_review_only_is_allowed(tmp_path) -> None:
    dataset = output_dataset(name="")
    blocked = OutputService(1024 * 1024).generate(loaded_pack(tmp_path), dataset).result
    assert blocked.issues[0].code == OutputIssueCode.OUTPUT_BLOCKED_BY_VALIDATION
    allowed = OutputService(1024 * 1024).generate(
        loaded_pack(tmp_path, validation_severity=RuleSeverity.REVIEW), dataset
    ).result
    assert allowed.success


def test_blocking_reconciliation_is_blocked_but_review_only_is_allowed(tmp_path) -> None:
    dataset = output_dataset()
    record = dataset.records[0]
    values = dict(record.values)
    values["expected_amount"] = values["expected_amount"].model_copy(update={"value": Decimal("99")})
    dataset = dataset.model_copy(update={"records": [record.model_copy(update={"values": values})]})
    blocked = OutputService(1024 * 1024).generate(loaded_pack(tmp_path), dataset).result
    assert blocked.issues[0].code == OutputIssueCode.OUTPUT_BLOCKED_BY_RECONCILIATION
    allowed = OutputService(1024 * 1024).generate(
        loaded_pack(tmp_path, reconciliation_severity=RuleSeverity.REVIEW), dataset
    ).result
    assert allowed.success
