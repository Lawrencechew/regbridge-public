from decimal import Decimal

import pytest

from app.canonical.models import CanonicalDataType
from app.imports.models import (
    DecimalConversion,
    FieldMapping,
    ImportIssueCode,
    StringConversion,
)
from tests.import_helpers import (
    NATIVE_ROW,
    NATIVE_VALUES,
    SYNTHETIC_CSV,
    import_service,
    synthetic_mapping,
    synthetic_schema,
    xlsx_bytes,
)


def test_csv_mapping_builds_typed_canonical_dataset_with_provenance() -> None:
    result = import_service().map(
        "customer.csv", SYNTHETIC_CSV, synthetic_mapping(), synthetic_schema()
    )

    assert result.success is True
    assert result.dataset is not None
    assert result.dataset_summary.record_count == 1
    record = result.dataset.records[0]
    assert record.record_id == "row-000002"
    assert record.values["amount"].value == Decimal("10.25")
    assert isinstance(record.values["amount"].value, Decimal)
    assert record.values["note"].value is None
    source = record.values["amount"].source
    assert source.source_name == "customer.csv"
    assert source.sheet is None
    assert source.row == 2
    assert source.column == "Amount"


def test_xlsx_mapping_accepts_native_values_and_sets_sheet_provenance() -> None:
    mapping = synthetic_mapping(sheet_name="Data")
    result = import_service().map(
        "customer.xlsx",
        xlsx_bytes([NATIVE_VALUES, NATIVE_ROW]),
        mapping,
        synthetic_schema(),
    )

    assert result.success is True
    assert result.dataset.records[0].values["event_date"].value.isoformat() == "2026-08-14"
    assert result.dataset.records[0].values["count"].source.sheet == "Data"


def test_blank_mapped_rows_are_skipped_without_renumbering_source_rows() -> None:
    content = (
        SYNTHETIC_CSV
        + b",,,,,,\n"
        + b"Beta,2,3.5,NO,15/08/2026,2026-08-15 10:00,x\n"
    )
    result = import_service().map(
        "customer.csv", content, synthetic_mapping(), synthetic_schema()
    )

    assert [record.record_id for record in result.dataset.records] == [
        "row-000002",
        "row-000004",
    ]


def test_conversion_failure_is_atomic_and_does_not_return_dataset() -> None:
    content = SYNTHETIC_CSV.replace(b",12,", b",12.5,")
    result = import_service().map(
        "customer.csv", content, synthetic_mapping(), synthetic_schema()
    )

    assert result.success is False
    assert result.dataset is None
    assert result.dataset_summary is None
    assert [issue.code for issue in result.issues] == [
        ImportIssueCode.IMPORT_VALUE_CONVERSION_FAILED
    ]


def test_empty_string_for_string_target_is_not_import_failure() -> None:
    content = SYNTHETIC_CSV.replace(b" Alpha ", b"")
    result = import_service().map(
        "customer.csv", content, synthetic_mapping(), synthetic_schema()
    )

    assert result.success is True
    assert result.dataset.records[0].values["name"].value == ""


def test_empty_non_string_cell_maps_to_typed_null_without_import_failure() -> None:
    content = SYNTHETIC_CSV.replace(b",12,", b",,")
    result = import_service().map(
        "customer.csv", content, synthetic_mapping(), synthetic_schema()
    )

    assert result.success is True
    value = result.dataset.records[0].values["count"]
    assert value.data_type == CanonicalDataType.INTEGER
    assert value.value is None


@pytest.mark.parametrize(
    ("mapping", "expected_code"),
    [
        (
            synthetic_mapping(
                fields=synthetic_mapping().fields
                + (synthetic_mapping().fields[0].model_copy(),)
            ),
            ImportIssueCode.DUPLICATE_SOURCE_MAPPING,
        ),
        (
            synthetic_mapping(
                fields=synthetic_mapping().fields
                + (
                    FieldMapping(
                        source_column_index=7,
                        target_field_id="name",
                        conversion=StringConversion(),
                    ),
                )
            ),
            ImportIssueCode.DUPLICATE_TARGET_MAPPING,
        ),
        (
            synthetic_mapping(fields=synthetic_mapping().fields[1:]),
            ImportIssueCode.MISSING_REQUIRED_MAPPING,
        ),
        (
            synthetic_mapping(
                fields=(
                    synthetic_mapping().fields[0].model_copy(
                        update={"source_column_index": 99}
                    ),
                )
                + synthetic_mapping().fields[1:]
            ),
            ImportIssueCode.SOURCE_COLUMN_NOT_FOUND,
        ),
        (
            synthetic_mapping(
                fields=(
                    synthetic_mapping().fields[0].model_copy(
                        update={"target_field_id": "unknown_field"}
                    ),
                )
                + synthetic_mapping().fields[1:]
            ),
            ImportIssueCode.TARGET_FIELD_NOT_FOUND,
        ),
        (
            synthetic_mapping(
                fields=(
                    synthetic_mapping().fields[0].model_copy(
                        update={"conversion": DecimalConversion()}
                    ),
                )
                + synthetic_mapping().fields[1:]
            ),
            ImportIssueCode.INCOMPATIBLE_CONVERSION,
        ),
    ],
)
def test_mapping_configuration_failures_are_reported_before_conversion(
    mapping, expected_code
) -> None:
    result = import_service().map(
        "customer.csv", SYNTHETIC_CSV, mapping, synthetic_schema()
    )

    assert result.success is False
    assert result.dataset is None
    assert expected_code in {issue.code for issue in result.issues}


def test_mapping_fingerprint_is_deterministic_and_content_sensitive() -> None:
    mapping = synthetic_mapping()
    assert mapping.fingerprint == synthetic_mapping().fingerprint
    changed = mapping.model_copy(
        update={
            "fields": (
                mapping.fields[0].model_copy(update={"source_column_index": 2}),
            )
            + mapping.fields[1:]
        }
    )
    assert changed.fingerprint != mapping.fingerprint


def test_file_fingerprint_depends_only_on_source_bytes() -> None:
    service = import_service()
    first = service.inspect("one.csv", SYNTHETIC_CSV)
    same = service.inspect("two.csv", SYNTHETIC_CSV)
    changed = service.inspect("one.csv", SYNTHETIC_CSV + b"\n")
    assert first.file_sha256 == same.file_sha256
    assert changed.file_sha256 != first.file_sha256


def test_mapped_formula_blocks_but_unmapped_formula_does_not() -> None:
    rows = [NATIVE_VALUES + ["Unused"], NATIVE_ROW + ["=1+1"]]
    content = xlsx_bytes(rows)
    success = import_service().map(
        "source.xlsx",
        content,
        synthetic_mapping(sheet_name="Data"),
        synthetic_schema(),
    )
    assert success.success is True

    rows[1][2] = "=1+1"
    failure = import_service().map(
        "source.xlsx",
        xlsx_bytes(rows),
        synthetic_mapping(sheet_name="Data"),
        synthetic_schema(),
    )
    assert failure.success is False
    assert [issue.code for issue in failure.issues] == [
        ImportIssueCode.FORMULA_CELL_UNSUPPORTED
    ]


def test_merged_mapped_header_is_rejected() -> None:
    from io import BytesIO
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet.append(NATIVE_VALUES)
    sheet.append(NATIVE_ROW)
    sheet.merge_cells("A1:B1")
    output = BytesIO()
    workbook.save(output)

    result = import_service().map(
        "source.xlsx",
        output.getvalue(),
        synthetic_mapping(sheet_name="Data"),
        synthetic_schema(),
    )
    assert result.success is False
    assert ImportIssueCode.MERGED_CELL_UNSUPPORTED in {
        issue.code for issue in result.issues
    }


def test_import_does_not_run_regulatory_validation() -> None:
    result = import_service().map(
        "customer.csv", SYNTHETIC_CSV, synthetic_mapping(), synthetic_schema()
    )
    assert result.success is True
    assert not hasattr(result, "validation_report")
