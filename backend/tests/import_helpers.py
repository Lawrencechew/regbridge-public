from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook

from app.canonical.models import (
    CanonicalDataType,
    CanonicalFieldDefinition,
    CanonicalSchema,
)
from app.imports.models import (
    BooleanConversion,
    DateConversion,
    DateTimeConversion,
    DecimalConversion,
    FieldMapping,
    ImportMapping,
    IntegerConversion,
    StringConversion,
)
from app.imports.security import ImportLimits
from app.imports.service import ImportService


def import_limits(**overrides) -> ImportLimits:
    values = {
        "max_file_size_bytes": 1024 * 1024,
        "max_rows": 100,
        "max_columns": 20,
        "max_xlsx_sheets": 5,
        "max_xlsx_zip_entries": 100,
        "max_xlsx_uncompressed_bytes": 5 * 1024 * 1024,
        "max_xlsx_compression_ratio": 100,
        "preview_rows": 2,
    }
    values.update(overrides)
    return ImportLimits(**values)


def import_service(**limits) -> ImportService:
    return ImportService(import_limits(**limits))


def synthetic_schema() -> CanonicalSchema:
    fields = (
        ("name", CanonicalDataType.STRING, True),
        ("count", CanonicalDataType.INTEGER, True),
        ("amount", CanonicalDataType.DECIMAL, True),
        ("active", CanonicalDataType.BOOLEAN, True),
        ("event_date", CanonicalDataType.DATE, True),
        ("processed_at", CanonicalDataType.DATETIME, True),
        ("note", CanonicalDataType.STRING, False),
    )
    return CanonicalSchema(
        id="synthetic-import",
        version="1.0.0",
        name="Synthetic Import Schema",
        fields=tuple(
            CanonicalFieldDefinition(
                id=field_id, name=field_id, data_type=data_type, required=required
            )
            for field_id, data_type, required in fields
        ),
    )


def synthetic_mapping(**overrides) -> ImportMapping:
    values = {
        "target_schema_id": "synthetic-import",
        "target_schema_version": "1.0.0",
        "header_row": 1,
        "fields": (
            FieldMapping(
                source_column_index=1,
                target_field_id="name",
                conversion=StringConversion(),
            ),
            FieldMapping(
                source_column_index=2,
                target_field_id="count",
                conversion=IntegerConversion(),
            ),
            FieldMapping(
                source_column_index=3,
                target_field_id="amount",
                conversion=DecimalConversion(),
            ),
            FieldMapping(
                source_column_index=4,
                target_field_id="active",
                conversion=BooleanConversion(true_values=("YES",), false_values=("NO",)),
            ),
            FieldMapping(
                source_column_index=5,
                target_field_id="event_date",
                conversion=DateConversion(date_format="%d/%m/%Y"),
            ),
            FieldMapping(
                source_column_index=6,
                target_field_id="processed_at",
                conversion=DateTimeConversion(datetime_format="%Y-%m-%d %H:%M"),
            ),
        ),
    }
    values.update(overrides)
    return ImportMapping(**values)


def xlsx_bytes(
    rows: list[list[object]],
    *,
    sheet_name: str = "Data",
    second_sheet: bool = False,
    hidden_second_sheet: bool = False,
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    for row in rows:
        sheet.append(row)
    if second_sheet:
        other = workbook.create_sheet("Other")
        other.append(["Other"])
        other.append([1])
        if hidden_second_sheet:
            other.sheet_state = "hidden"
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


SYNTHETIC_CSV = (
    "Name,Count,Amount,Active,Date,Processed,Ignored\n"
    " Alpha ,12,10.25,YES,14/08/2026,2026-08-14 09:30,x\n"
).encode()

NATIVE_VALUES = [
    "Name",
    "Count",
    "Amount",
    "Active",
    "Date",
    "Processed",
]

NATIVE_ROW = ["Alpha", 12.0, 10.25, "YES", date(2026, 8, 14), datetime(2026, 8, 14, 9, 30)]
