from enum import StrEnum

from pydantic import BaseModel, ConfigDict, ValidationError

from app.canonical.models import (
    CanonicalDataType,
    CanonicalDataset,
    SourceReference,
    canonical_value_matches_type,
)


class StructuralIssueCode(StrEnum):
    DUPLICATE_RECORD_ID = "DUPLICATE_RECORD_ID"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_VALUE_TYPE = "INVALID_VALUE_TYPE"
    INVALID_SOURCE_REFERENCE = "INVALID_SOURCE_REFERENCE"


class StructuralIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: StructuralIssueCode
    message: str
    record_id: str | None = None
    field_id: str | None = None


class StructuralValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    issues: list[StructuralIssue]


class CanonicalStructuralValidator:
    def validate(self, dataset: CanonicalDataset) -> StructuralValidationResult:
        issues: list[StructuralIssue] = []
        schema_fields = dataset.canonical_schema.fields_by_id
        seen_record_ids: set[str] = set()

        for record in dataset.records:
            if record.record_id in seen_record_ids:
                issues.append(
                    StructuralIssue(
                        code=StructuralIssueCode.DUPLICATE_RECORD_ID,
                        message=f"Record ID '{record.record_id}' is duplicated.",
                        record_id=record.record_id,
                    )
                )
            seen_record_ids.add(record.record_id)

            for field_id in record.values:
                if field_id not in schema_fields:
                    issues.append(
                        StructuralIssue(
                            code=StructuralIssueCode.UNKNOWN_FIELD,
                            message=f"Canonical field '{field_id}' is not defined by the schema.",
                            record_id=record.record_id,
                            field_id=field_id,
                        )
                    )

            for field_id, definition in schema_fields.items():
                if definition.required and field_id not in record.values:
                    issues.append(
                        StructuralIssue(
                            code=StructuralIssueCode.MISSING_REQUIRED_FIELD,
                            message=f"Required canonical field '{field_id}' is missing.",
                            record_id=record.record_id,
                            field_id=field_id,
                        )
                    )

            for field_id, canonical_value in record.values.items():
                definition = schema_fields.get(field_id)
                if definition is None:
                    continue
                if canonical_value.value is not None and (
                    canonical_value.data_type != definition.data_type
                    or not canonical_value_matches_type(
                        canonical_value.value, definition.data_type
                    )
                ):
                    issues.append(
                        StructuralIssue(
                            code=StructuralIssueCode.INVALID_VALUE_TYPE,
                            message=(
                                f"Canonical field '{field_id}' does not contain a "
                                f"{definition.data_type.value} value."
                            ),
                            record_id=record.record_id,
                            field_id=field_id,
                        )
                    )
                if canonical_value.source is not None and not self._valid_source(
                    canonical_value.source
                ):
                    issues.append(
                        StructuralIssue(
                            code=StructuralIssueCode.INVALID_SOURCE_REFERENCE,
                            message=f"Canonical field '{field_id}' has invalid source provenance.",
                            record_id=record.record_id,
                            field_id=field_id,
                        )
                    )

        return StructuralValidationResult(valid=not issues, issues=issues)

    @staticmethod
    def _valid_source(source: SourceReference) -> bool:
        try:
            SourceReference.model_validate(source.model_dump())
        except ValidationError:
            return False
        return True
