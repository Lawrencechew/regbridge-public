from datetime import date
from io import BytesIO

from openpyxl import Workbook

from app.canonical.models import CanonicalDataType, CanonicalFieldDefinition, CanonicalSchema
from app.imports.models import (
    FieldMapping, ImportMapping, SectionImportMapping, StringConversion,
    WorkflowImportMapping,
)
from app.imports.security import ImportLimits
from app.imports.service import ImportService
from app.regpacks.models import LoadedRegPack, RegPackManifest
from app.regpacks.workflow import LoadedRegPackSection, WorkflowDefinition
from app.regpacks.workflow_engine import WorkflowRunner
from app.validation.models import RequiredRule, RuleSet, RuleSeverity


def test_synthetic_inventory_workflow_proves_sections_are_not_regulator_specific():
    receipts_schema = CanonicalSchema(
        id="inventory-receipts", version="1.0.0", name="Receipts",
        fields=(CanonicalFieldDefinition(id="item", name="Item", data_type=CanonicalDataType.STRING, required=True),),
    )
    dispatches_schema = CanonicalSchema(
        id="inventory-dispatches", version="1.0.0", name="Dispatches",
        fields=(CanonicalFieldDefinition(id="item", name="Item", data_type=CanonicalDataType.STRING, required=True),),
    )
    rules = lambda identifier: RuleSet(
        id=identifier, version="1.0.0", name=identifier,
        rules=(RequiredRule(
            id=f"{identifier}-001", name="Item required", description="Each row has an item.",
            severity=RuleSeverity.BLOCKING, field_id="item", source_refs=("EXAMPLE-SOURCE",),
        ),),
    )
    workflow = WorkflowDefinition(
        id="inventory-example", version="1.0.0",
        sections=(
            {"id": "receipts", "name": "Receipts", "optional": False, "canonical_schema": "receipts.yaml", "validation_rules": "receipts-rules.yaml"},
            {"id": "dispatches", "name": "Dispatches", "optional": False, "canonical_schema": "dispatches.yaml", "validation_rules": "dispatches-rules.yaml"},
        ),
    )
    manifest = RegPackManifest.model_validate({
        "schema_version": "1.2", "id": "inventory-example", "name": "Inventory Example",
        "regulator": {"code": "EX", "name": "Example"}, "version": "1.0.0",
        "effective": {"from": date(2026, 1, 1)}, "description": "Synthetic multi-section test pack.",
        "status": "verified",
        "reporting": {"record_period": {"frequency": "monthly"}, "submission": {"frequency": "monthly"}},
        "components": {"workflow": "workflow.yaml"},
        "sources": [{"id": "EXAMPLE-SOURCE", "title": "Synthetic source", "publisher": "Tests", "url": "https://example.test/source", "checked_at": date(2026, 1, 1)}],
    })
    loaded = LoadedRegPack(
        manifest=manifest, fingerprint="0" * 64, workflow_definition=workflow,
        sections=(
            LoadedRegPackSection("receipts", "Receipts", None, False, receipts_schema, rules("EX-RECEIPTS"), None),
            LoadedRegPackSection("dispatches", "Dispatches", None, False, dispatches_schema, rules("EX-DISPATCHES"), None),
        ),
    )
    book = Workbook()
    receipts = book.active
    receipts.title = "Receipts"
    receipts.append(["Item"])
    receipts.append(["Widget"])
    dispatches = book.create_sheet("Dispatches")
    dispatches.append(["Item"])
    dispatches.append(["Widget"])
    stream = BytesIO()
    book.save(stream)
    mapping = WorkflowImportMapping(sections=(
        SectionImportMapping(section_id="receipts", mapping=ImportMapping(
            target_schema_id="inventory-receipts", target_schema_version="1.0.0", sheet_name="Receipts",
            fields=(FieldMapping(source_column_index=1, target_field_id="item", conversion=StringConversion()),),
        )),
        SectionImportMapping(section_id="dispatches", mapping=ImportMapping(
            target_schema_id="inventory-dispatches", target_schema_version="1.0.0", sheet_name="Dispatches",
            fields=(FieldMapping(source_column_index=1, target_field_id="item", conversion=StringConversion()),),
        )),
    ))
    imports = ImportService(ImportLimits(
        max_file_size_bytes=1024 * 1024, max_rows=20, max_columns=10, max_xlsx_sheets=5,
        max_xlsx_zip_entries=100, max_xlsx_uncompressed_bytes=5 * 1024 * 1024,
        max_xlsx_compression_ratio=100, preview_rows=2,
    ))
    imported = imports.map_workflow("inventory.xlsx", stream.getvalue(), mapping, loaded)
    result = WorkflowRunner().run(
        loaded, imported.datasets, {}, bundle_id="inventory-example-run"
    )
    assert result.ready
    assert [item.section_id for item in result.sections] == ["receipts", "dispatches"]
    assert all(item.reconciliation_status == "not_applicable" for item in result.sections)
