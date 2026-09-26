import logging
from uuid import uuid4

from app.canonical.models import CanonicalDataset, CanonicalSchema
from app.imports.inspector import SourceInspector
from app.imports.mapper import MappingEngine
from app.imports.errors import ImportRequestError
from app.imports.models import (
    ImportIssueCode,
    ImportMapping,
    ImportResult,
    ImportedDatasetSummary,
    SourceFileInspection,
    WorkflowImportMapping,
    WorkflowImportResult,
    WorkflowSectionImportResult,
)
from app.regpacks.models import LoadedRegPack
from app.imports.security import ImportLimits

logger = logging.getLogger(__name__)


class ImportService:
    def __init__(self, limits: ImportLimits, mapping_max_characters: int = 250_000) -> None:
        self.inspector = SourceInspector(limits)
        self.mapper = MappingEngine()
        self.mapping_max_characters = mapping_max_characters

    @property
    def max_file_size_bytes(self) -> int:
        return self.inspector.limits.max_file_size_bytes

    def enforce_payload_size(self, *values: str | None) -> None:
        if any(value is not None and len(value) > self.mapping_max_characters for value in values):
            raise ImportRequestError(
                ImportIssueCode.INVALID_MAPPING,
                "The mapping payload exceeds the configured size limit.",
                413,
            )

    def inspect(
        self,
        source_name: str,
        content: bytes,
        *,
        sheet_name: str | None = None,
        header_row: int = 1,
    ) -> SourceFileInspection:
        inspection = self.inspector.inspect(
            source_name,
            content,
            sheet_name=sheet_name,
            header_row=header_row,
        ).inspection
        logger.info(
            "Import inspected: type=%s size=%d sheets=%d rows=%s columns=%d",
            inspection.source_type,
            inspection.file_size_bytes,
            len(inspection.sheets),
            inspection.data_row_count,
            len(inspection.columns),
        )
        return inspection

    def map(
        self,
        source_name: str,
        content: bytes,
        mapping: ImportMapping,
        schema: CanonicalSchema,
    ) -> ImportResult:
        source = self.inspector.inspect(
            source_name,
            content,
            sheet_name=mapping.sheet_name,
            header_row=mapping.header_row,
        )
        return self.mapper.map(source, mapping, schema)

    def map_workflow(
        self,
        source_name: str,
        content: bytes,
        mapping: WorkflowImportMapping,
        pack: LoadedRegPack,
    ) -> WorkflowImportResult:
        if pack.workflow_definition is None or not pack.sections:
            raise ImportRequestError(
                ImportIssueCode.INVALID_MAPPING,
                "The selected RegPack does not define a sectioned workflow.",
                422,
            )
        definitions = {section.id: section for section in pack.sections}
        supplied = {section.section_id: section for section in mapping.sections}
        if set(supplied) != set(definitions):
            raise ImportRequestError(
                ImportIssueCode.INVALID_MAPPING,
                "The workflow mapping must address every declared section.",
                422,
            )
        active = []
        for section_id, item in supplied.items():
            definition = definitions[section_id]
            if item.mapping is None:
                if not definition.optional:
                    raise ImportRequestError(
                        ImportIssueCode.INVALID_MAPPING,
                        "A required workflow section cannot be omitted.",
                        422,
                    )
                continue
            if item.mapping.sheet_name is None:
                raise ImportRequestError(
                    ImportIssueCode.SHEET_SELECTION_REQUIRED,
                    "Each active workflow section requires an XLSX worksheet.",
                    422,
                )
            active.append((section_id, item.mapping))
        tables = self.inspector.inspect_many(
            source_name,
            content,
            tuple((item.sheet_name, item.header_row) for _, item in active),
        )
        table_by_section = {
            section_id: table for (section_id, _), table in zip(active, tables, strict=True)
        }
        datasets: dict[str, CanonicalDataset] = {}
        results: list[WorkflowSectionImportResult] = []
        success = True
        for section in pack.sections:
            item = supplied[section.id]
            if item.mapping is None:
                dataset = CanonicalDataset(
                    dataset_id=f"{section.id}-{uuid4()}",
                    schema=section.canonical_schema,
                    records=[],
                    metadata={"section_id": section.id, "omitted": True},
                )
                datasets[section.id] = dataset
                results.append(WorkflowSectionImportResult(
                    section_id=section.id,
                    success=True,
                    omitted=True,
                    dataset_summary=ImportedDatasetSummary(
                        dataset_id=dataset.dataset_id,
                        schema_id=section.canonical_schema.id,
                        schema_version=section.canonical_schema.version,
                        record_count=0,
                        preview_count=0,
                    ),
                ))
                continue
            result = self.mapper.map(
                table_by_section[section.id], item.mapping, section.canonical_schema
            )
            success = success and result.success
            if result.dataset is not None:
                result.dataset.metadata["section_id"] = section.id
                datasets[section.id] = result.dataset
            results.append(WorkflowSectionImportResult(
                section_id=section.id,
                success=result.success,
                source=result.source,
                mapping_fingerprint=result.mapping_fingerprint,
                dataset_summary=result.dataset_summary or ImportedDatasetSummary(
                    dataset_id=f"failed-{section.id}",
                    schema_id=section.canonical_schema.id,
                    schema_version=section.canonical_schema.version,
                    record_count=0,
                    preview_count=0,
                ),
                dataset_preview=result.dataset_preview,
                issues=result.issues,
            ))
        logger.info(
            "Workflow import mapped: pack=%s sections=%d records=%d blocking=%d",
            pack.id,
            len(pack.sections),
            sum(len(dataset.records) for dataset in datasets.values()),
            sum(len(item.issues) for item in results),
        )
        return WorkflowImportResult(
            success=success and len(datasets) == len(pack.sections),
            mapping_fingerprint=mapping.fingerprint,
            sections=tuple(results),
            datasets=datasets,
        )
