from io import BytesIO

import pytest
from openpyxl import Workbook

from app.imports.errors import ImportRequestError
from app.imports.models import ImportIssueCode
from tests.import_helpers import import_service, xlsx_bytes


def test_csv_inspection_preserves_blank_duplicate_headers_and_quoted_commas() -> None:
    source = b'Name,,Name\n"Alpha, Ltd",,10\nBeta,,20\nGamma,,30\n'
    inspection = import_service().inspect("source.csv", source)

    assert [column.header for column in inspection.columns] == ["Name", None, "Name"]
    assert inspection.data_row_count == 3
    assert len(inspection.preview_rows) == 2
    assert inspection.preview_rows[0].values[0] == "Alpha, Ltd"
    assert inspection.selected_sheet is None


def test_csv_utf8_bom_and_explicit_header_row_are_supported() -> None:
    source = b"\xef\xbb\xbfintro\nA,B\n1,2\n"
    inspection = import_service().inspect("source.csv", source, header_row=2)

    assert [column.header for column in inspection.columns] == ["A", "B"]
    assert inspection.preview_rows[0].source_row == 3


def test_single_visible_xlsx_sheet_is_selected_and_formulas_are_detected() -> None:
    content = xlsx_bytes([["Name", "Amount"], ["Alpha", "=1+1"]])
    inspection = import_service().inspect("source.xlsx", content)

    assert inspection.selected_sheet == "Data"
    assert inspection.formula_cells_detected is True
    assert inspection.columns[0].excel_column == "A"
    assert inspection.preview_rows[0].values[1] == {"formula": True}


def test_xlsx_blank_duplicate_headers_and_dimensions_are_preserved() -> None:
    content = xlsx_bytes([["Name", None, "Name"], ["Alpha", None, 1]])
    inspection = import_service().inspect("source.xlsx", content)

    assert [column.header for column in inspection.columns] == ["Name", None, "Name"]
    assert inspection.data_row_count == 1
    assert inspection.sheets[0].row_count == 1
    assert inspection.sheets[0].column_count == 3


def test_xlsx_explicit_header_row_is_one_based() -> None:
    content = xlsx_bytes([["Introduction"], ["A"], [1]])
    inspection = import_service().inspect("source.xlsx", content, header_row=2)

    assert inspection.columns[0].header == "A"
    assert inspection.preview_rows[0].source_row == 3


def test_multiple_visible_sheets_require_explicit_selection() -> None:
    content = xlsx_bytes([["Name"], ["Alpha"]], second_sheet=True)
    inspection = import_service().inspect("source.xlsx", content)

    assert inspection.selection_required is True
    assert inspection.selected_sheet is None
    assert [sheet.name for sheet in inspection.sheets] == ["Data", "Other"]
    assert inspection.columns == ()

    selected = import_service().inspect("source.xlsx", content, sheet_name="Other")
    assert selected.selected_sheet == "Other"


def test_multi_sheet_inspection_detects_formulas_without_selecting_a_sheet() -> None:
    content = xlsx_bytes([["Name", "Amount"], ["Alpha", "=1+1"]], second_sheet=True)
    inspection = import_service().inspect("source.xlsx", content)

    assert inspection.selection_required is True
    assert inspection.formula_cells_detected is True


def test_hidden_sheet_is_listed_but_not_silently_selected() -> None:
    content = xlsx_bytes(
        [["Name"], ["Alpha"]], second_sheet=True, hidden_second_sheet=True
    )
    inspection = import_service().inspect("source.xlsx", content)

    assert inspection.selected_sheet == "Data"
    assert inspection.sheets[1].visibility == "hidden"


def test_missing_sheet_is_controlled() -> None:
    content = xlsx_bytes([["Name"], ["Alpha"]])
    with pytest.raises(ImportRequestError) as error:
        import_service().inspect("source.xlsx", content, sheet_name="Missing")

    assert error.value.code == ImportIssueCode.SHEET_NOT_FOUND


def test_xlsx_table_limits_and_header_row_are_enforced() -> None:
    content = xlsx_bytes([["A", "B"], [1, 2], [3, 4]])
    with pytest.raises(ImportRequestError) as rows_error:
        import_service(max_rows=1).inspect("source.xlsx", content)
    assert rows_error.value.code == ImportIssueCode.SOURCE_LIMIT_EXCEEDED

    with pytest.raises(ImportRequestError) as header_error:
        import_service().inspect("source.xlsx", content, header_row=4)
    assert header_error.value.code == ImportIssueCode.INVALID_HEADER_ROW


def test_merged_ranges_are_retained_for_mapping_safety() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Combined", None])
    sheet.append(["Alpha", "Beta"])
    sheet.merge_cells("A1:B1")
    output = BytesIO()
    workbook.save(output)

    table = import_service().inspector.inspect("source.xlsx", output.getvalue())
    assert table.merged_ranges == ((1, 1, 2, 1),)
