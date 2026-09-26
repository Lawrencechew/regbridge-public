from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.imports.errors import ImportRequestError
from app.imports.models import ImportIssueCode
from app.imports.security import inspect_xlsx_container
from tests.import_helpers import import_limits, import_service


@pytest.mark.parametrize("name", ["source.exe", "source.pdf", "source.xls", "source.xlsm"])
def test_unsupported_extensions_are_rejected(name: str) -> None:
    with pytest.raises(ImportRequestError) as error:
        import_service().inspect(name, b"content")

    assert error.value.code == ImportIssueCode.UNSUPPORTED_FILE_TYPE


@pytest.mark.parametrize("content", [b"plain text", b"PK malformed"])
def test_fake_or_malformed_xlsx_is_rejected(content: bytes) -> None:
    with pytest.raises(ImportRequestError) as error:
        import_service().inspect("source.xlsx", content)

    assert error.value.code == ImportIssueCode.INVALID_XLSX


def test_file_size_limit_is_checked_before_parsing() -> None:
    with pytest.raises(ImportRequestError) as error:
        import_service(max_file_size_bytes=3).inspect("source.xlsx", b"not-xlsx")

    assert error.value.code == ImportIssueCode.FILE_TOO_LARGE
    assert error.value.status_code == 413


def synthetic_archive(extra_entries: int = 0, payload: bytes = b"") -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("xl/workbook.xml", b"<workbook/>")
        for index in range(extra_entries):
            archive.writestr(f"xl/item-{index}.xml", b"x")
        if payload:
            archive.writestr("xl/payload.bin", payload)
    return output.getvalue()


def test_xlsx_zip_entry_limit_is_enforced() -> None:
    with pytest.raises(ImportRequestError) as error:
        inspect_xlsx_container(
            synthetic_archive(extra_entries=2),
            import_limits(max_xlsx_zip_entries=3),
        )

    assert error.value.code == ImportIssueCode.XLSX_SECURITY_LIMIT_EXCEEDED


def test_xlsx_uncompressed_size_limit_is_enforced() -> None:
    with pytest.raises(ImportRequestError) as error:
        inspect_xlsx_container(
            synthetic_archive(payload=b"x" * 1000),
            import_limits(max_xlsx_uncompressed_bytes=100),
        )

    assert error.value.code == ImportIssueCode.XLSX_SECURITY_LIMIT_EXCEEDED


def test_xlsx_compression_ratio_limit_is_enforced() -> None:
    with pytest.raises(ImportRequestError) as error:
        inspect_xlsx_container(
            synthetic_archive(payload=b"x" * 10_000),
            import_limits(max_xlsx_compression_ratio=2),
        )

    assert error.value.code == ImportIssueCode.XLSX_SECURITY_LIMIT_EXCEEDED


@pytest.mark.parametrize("content", [b"A,B\x00C", b"\xff\xfeA\x00"])
def test_binary_or_unsupported_csv_encoding_is_rejected(content: bytes) -> None:
    with pytest.raises(ImportRequestError) as error:
        import_service().inspect("source.csv", content)

    assert error.value.code == ImportIssueCode.UNSUPPORTED_TEXT_ENCODING
