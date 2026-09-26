from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.canonical.validation import StructuralValidationResult


class ValidationEngineError(Exception):
    """Base error for controlled validation-engine failures."""


class RuleSetConfigurationError(ValidationEngineError):
    """A RuleSet is incompatible with the canonical schema."""


class DatasetNotStructurallyValidError(ValidationEngineError):
    """Rule validation cannot run on a structurally invalid dataset."""

    def __init__(self, result: "StructuralValidationResult") -> None:
        super().__init__("The canonical dataset must be structurally valid before rule validation.")
        self.result = result
