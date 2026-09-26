import logging
from collections import Counter

from app.canonical.builder import CanonicalDatasetBuilder
from app.canonical.errors import CanonicalDatasetError
from app.canonical.models import (
    CanonicalDataset,
    CanonicalSchema,
    CanonicalValue,
    SourceReference,
)
from app.imports.conversion import ConversionFailedError, convert_source_value
from app.imports.inspector import SourceTable
from app.imports.models import (
    ImportIssue,
    ImportIssueCode,
    ImportIssueSeverity,
    ImportMapping,
    ImportResult,
    ImportedDatasetSummary,
    SourceType,
)

logger = logging.getLogger(__name__)


class MappingEngine:
    def map(
        self, source: SourceTable, mapping: ImportMapping, schema: CanonicalSchema
    ) -> ImportResult:
        fingerprint = mapping.fingerprint
        configuration_issues = self._validate_mapping(source, mapping, schema)
        if configuration_issues:
            return self._failure(source, fingerprint, configuration_issues)

        converted_records: list[tuple[str, dict[str, CanonicalValue]]] = []
        issues: list[ImportIssue] = []
        fields_by_id = schema.fields_by_id
        columns_by_index = {
            column.index: column for column in source.inspection.columns
        }
        for row in source.rows:
            mapped_cells = [
                row.cells[field.source_column_index - 1] for field in mapping.fields
            ]
            if mapping.skip_blank_rows and all(
                cell.value is None or cell.value == "" for cell in mapped_cells
            ):
                continue
            values: dict[str, CanonicalValue] = {}
            for field in mapping.fields:
                cell = row.cells[field.source_column_index - 1]
                column = columns_by_index[field.source_column_index]
                source_reference = SourceReference(
                    source_name=source.inspection.source_name,
                    sheet=source.inspection.selected_sheet,
                    row=row.source_row,
                    column=(
                        column.header
                        or (
                            f"Column {column.excel_column}"
                            if column.excel_column is not None
                            else f"Column {column.index}"
                        )
                    ),
                )
                if self._is_merged(
                    source, row.source_row, field.source_column_index
                ):
                    issues.append(
                        ImportIssue(
                            code=ImportIssueCode.MERGED_CELL_UNSUPPORTED,
                            message="Mapped merged cells cannot be interpreted safely.",
                            severity=ImportIssueSeverity.BLOCKING,
                            source=source_reference,
                            target_field_id=field.target_field_id,
                            expected_type=field.conversion.type,
                        )
                    )
                    continue
                if cell.is_formula:
                    issues.append(
                        ImportIssue(
                            code=ImportIssueCode.FORMULA_CELL_UNSUPPORTED,
                            message="Mapped formula cells cannot be canonicalised.",
                            severity=ImportIssueSeverity.BLOCKING,
                            source=source_reference,
                            target_field_id=field.target_field_id,
                            expected_type=field.conversion.type,
                        )
                    )
                    continue
                try:
                    converted = convert_source_value(cell.value, field.conversion)
                except ConversionFailedError:
                    issues.append(
                        ImportIssue(
                            code=ImportIssueCode.IMPORT_VALUE_CONVERSION_FAILED,
                            message=(
                                "A mapped source value could not be converted to "
                                f"{field.conversion.type.value}."
                            ),
                            severity=ImportIssueSeverity.BLOCKING,
                            source=source_reference,
                            target_field_id=field.target_field_id,
                            expected_type=field.conversion.type,
                        )
                    )
                    continue
                values[field.target_field_id] = CanonicalValue(
                    data_type=field.conversion.type,
                    value=converted,
                    source=source_reference,
                )
            for field_id, definition in fields_by_id.items():
                if field_id not in values and field_id not in {
                    item.target_field_id for item in mapping.fields
                }:
                    values[field_id] = CanonicalValue(
                        data_type=definition.data_type, value=None
                    )
            converted_records.append((f"row-{row.source_row:06d}", values))

        if issues:
            logger.info(
                "Mapping failed: file_sha256=%s issues=%d",
                source.inspection.file_sha256,
                len(issues),
            )
            return self._failure(source, fingerprint, issues)

        dataset_id = (
            f"import-{source.inspection.file_sha256[:12]}-{fingerprint[:12]}"
        )
        builder = CanonicalDatasetBuilder(
            schema=schema,
            dataset_id=dataset_id,
            metadata={
                "source_file_sha256": source.inspection.file_sha256,
                "mapping_fingerprint": fingerprint,
                "source_type": source.inspection.source_type.value,
            },
        )
        try:
            for record_id, values in converted_records:
                builder.add_record(record_id, values)
            dataset = builder.build()
        except CanonicalDatasetError as exc:
            issue = ImportIssue(
                code=ImportIssueCode.INCOMPATIBLE_CONVERSION,
                message="Mapped values did not satisfy the canonical schema.",
                severity=ImportIssueSeverity.BLOCKING,
            )
            return self._failure(source, fingerprint, [issue])
        preview = tuple(dataset.records[:10])
        return ImportResult(
            success=True,
            source=source.inspection,
            mapping_fingerprint=fingerprint,
            dataset=dataset,
            dataset_summary=ImportedDatasetSummary(
                dataset_id=dataset.dataset_id,
                schema_id=schema.id,
                schema_version=schema.version,
                record_count=len(dataset.records),
                preview_count=len(preview),
            ),
            dataset_preview=preview,
        )

    @staticmethod
    def _failure(
        source: SourceTable, fingerprint: str, issues: list[ImportIssue]
    ) -> ImportResult:
        return ImportResult(
            success=False,
            source=source.inspection,
            mapping_fingerprint=fingerprint,
            dataset=None,
            dataset_summary=None,
            issues=tuple(issues),
        )

    @staticmethod
    def _validate_mapping(
        source: SourceTable, mapping: ImportMapping, schema: CanonicalSchema
    ) -> list[ImportIssue]:
        issues: list[ImportIssue] = []
        if source.inspection.selection_required:
            issues.append(
                ImportIssue(
                    code=ImportIssueCode.SHEET_SELECTION_REQUIRED,
                    message="An explicit worksheet selection is required.",
                    severity=ImportIssueSeverity.BLOCKING,
                )
            )
            return issues
        if (
            mapping.target_schema_id != schema.id
            or mapping.target_schema_version != schema.version
        ):
            issues.append(
                ImportIssue(
                    code=ImportIssueCode.INCOMPATIBLE_CONVERSION,
                    message="The mapping target does not match the selected schema.",
                    severity=ImportIssueSeverity.BLOCKING,
                )
            )
        source_indexes = [field.source_column_index for field in mapping.fields]
        target_fields = [field.target_field_id for field in mapping.fields]
        for index, count in Counter(source_indexes).items():
            if count > 1:
                issues.append(
                    ImportIssue(
                        code=ImportIssueCode.DUPLICATE_SOURCE_MAPPING,
                        message=f"Source column {index} is mapped more than once.",
                        severity=ImportIssueSeverity.BLOCKING,
                    )
                )
        for field_id, count in Counter(target_fields).items():
            if count > 1:
                issues.append(
                    ImportIssue(
                        code=ImportIssueCode.DUPLICATE_TARGET_MAPPING,
                        message=f"Canonical field '{field_id}' is mapped more than once.",
                        severity=ImportIssueSeverity.BLOCKING,
                        target_field_id=field_id,
                    )
                )
        available_columns = {column.index for column in source.inspection.columns}
        for field in mapping.fields:
            if field.source_column_index not in available_columns:
                issues.append(
                    ImportIssue(
                        code=ImportIssueCode.SOURCE_COLUMN_NOT_FOUND,
                        message=(
                            f"Source column {field.source_column_index} was not found."
                        ),
                        severity=ImportIssueSeverity.BLOCKING,
                        target_field_id=field.target_field_id,
                    )
                )
            elif MappingEngine._is_merged(
                source, mapping.header_row, field.source_column_index
            ):
                issues.append(
                    ImportIssue(
                        code=ImportIssueCode.MERGED_CELL_UNSUPPORTED,
                        message="Mapped merged headers cannot be interpreted safely.",
                        severity=ImportIssueSeverity.BLOCKING,
                        target_field_id=field.target_field_id,
                    )
                )
            definition = schema.fields_by_id.get(field.target_field_id)
            if definition is None:
                issues.append(
                    ImportIssue(
                        code=ImportIssueCode.TARGET_FIELD_NOT_FOUND,
                        message=(
                            f"Canonical field '{field.target_field_id}' was not found."
                        ),
                        severity=ImportIssueSeverity.BLOCKING,
                        target_field_id=field.target_field_id,
                    )
                )
            elif definition.data_type != field.conversion.type:
                issues.append(
                    ImportIssue(
                        code=ImportIssueCode.INCOMPATIBLE_CONVERSION,
                        message=(
                            f"Conversion for '{field.target_field_id}' does not match "
                            "the canonical field type."
                        ),
                        severity=ImportIssueSeverity.BLOCKING,
                        target_field_id=field.target_field_id,
                        expected_type=definition.data_type,
                    )
                )
        mapped_targets = set(target_fields)
        for definition in schema.fields:
            if definition.required and definition.id not in mapped_targets:
                issues.append(
                    ImportIssue(
                        code=ImportIssueCode.MISSING_REQUIRED_MAPPING,
                        message=(
                            f"Required canonical field '{definition.id}' is not mapped."
                        ),
                        severity=ImportIssueSeverity.BLOCKING,
                        target_field_id=definition.id,
                        expected_type=definition.data_type,
                    )
                )
        return issues

    @staticmethod
    def _is_merged(source: SourceTable, row: int, column: int) -> bool:
        return any(
            min_column <= column <= max_column and min_row <= row <= max_row
            for min_column, min_row, max_column, max_row in source.merged_ranges
        )
