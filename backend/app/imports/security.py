from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from app.core.config import Settings
from app.imports.errors import ImportRequestError
from app.imports.models import ImportIssueCode, SourceType


@dataclass(frozen=True)
class ImportLimits:
    max_file_size_bytes: int
    max_rows: int
    max_columns: int
    max_xlsx_sheets: int
    max_xlsx_zip_entries: int
    max_xlsx_uncompressed_bytes: int
    max_xlsx_compression_ratio: float
    preview_rows: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "ImportLimits":
        return cls(
            max_file_size_bytes=settings.import_max_file_size_mb * 1024 * 1024,
            max_rows=settings.import_max_rows,
            max_columns=settings.import_max_columns,
            max_xlsx_sheets=settings.import_max_xlsx_sheets,
            max_xlsx_zip_entries=settings.import_max_xlsx_zip_entries,
            max_xlsx_uncompressed_bytes=(
                settings.import_max_xlsx_uncompressed_mb * 1024 * 1024
            ),
            max_xlsx_compression_ratio=settings.import_max_xlsx_compression_ratio,
            preview_rows=settings.import_preview_rows,
        )


def source_type_for_name(source_name: str) -> SourceType:
    suffix = Path(source_name).suffix.lower()
    if suffix == ".csv":
        return SourceType.CSV
    if suffix == ".xlsx":
        return SourceType.XLSX
    raise ImportRequestError(
        ImportIssueCode.UNSUPPORTED_FILE_TYPE,
        "Only .csv and .xlsx source files are supported.",
        400,
    )


def enforce_file_size(content: bytes, limits: ImportLimits) -> None:
    if len(content) > limits.max_file_size_bytes:
        raise ImportRequestError(
            ImportIssueCode.FILE_TOO_LARGE,
            "The uploaded source file exceeds the configured size limit.",
            413,
        )


def inspect_xlsx_container(content: bytes, limits: ImportLimits) -> bool:
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise ImportRequestError(
                    ImportIssueCode.INVALID_XLSX,
                    "The uploaded file is not a valid XLSX workbook.",
                )
            if len(entries) > limits.max_xlsx_zip_entries:
                raise _xlsx_limit_error()
            uncompressed = sum(entry.file_size for entry in entries)
            compressed = sum(entry.compress_size for entry in entries)
            if uncompressed > limits.max_xlsx_uncompressed_bytes:
                raise _xlsx_limit_error()
            ratio = uncompressed / max(compressed, 1)
            if ratio > limits.max_xlsx_compression_ratio or any(
                entry.file_size / max(entry.compress_size, 1)
                > limits.max_xlsx_compression_ratio
                for entry in entries
            ):
                raise _xlsx_limit_error()
            if any(entry.flag_bits & 0x1 for entry in entries):
                raise ImportRequestError(
                    ImportIssueCode.INVALID_XLSX,
                    "Encrypted XLSX entries are not supported.",
                )
            if "xl/vbaProject.bin" in names:
                raise ImportRequestError(
                    ImportIssueCode.UNSUPPORTED_FILE_TYPE,
                    "Macro-enabled workbooks are not supported.",
                )
            content_types = archive.read("[Content_Types].xml").lower()
            if b"macroenabled" in content_types or b"vba" in content_types:
                raise ImportRequestError(
                    ImportIssueCode.UNSUPPORTED_FILE_TYPE,
                    "Macro-enabled workbooks are not supported.",
                )
            return any(name.startswith("xl/externalLinks/") for name in names)
    except ImportRequestError:
        raise
    except (BadZipFile, OSError, KeyError, RuntimeError) as exc:
        raise ImportRequestError(
            ImportIssueCode.INVALID_XLSX,
            "The uploaded file is not a valid XLSX workbook.",
        ) from exc


def _xlsx_limit_error() -> ImportRequestError:
    return ImportRequestError(
        ImportIssueCode.XLSX_SECURITY_LIMIT_EXCEEDED,
        "The XLSX container exceeds a configured security limit.",
        413,
    )
