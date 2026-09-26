from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.canonical.validation import StructuralValidationResult


class CanonicalDataError(Exception):
    """Base error for predictable canonical-data failures."""


class CanonicalSchemaNotFoundError(CanonicalDataError):
    """A requested canonical schema or version is not registered."""


class DuplicateCanonicalSchemaError(CanonicalDataError):
    """A schema ID and version has already been registered."""


class CanonicalDatasetError(CanonicalDataError):
    """A builder operation would create a structurally invalid dataset."""

    def __init__(self, message: str, result: "StructuralValidationResult | None" = None) -> None:
        super().__init__(message)
        self.result = result
