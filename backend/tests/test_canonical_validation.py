from datetime import date

from app.canonical.models import (
    CanonicalDataType,
    CanonicalDataset,
    CanonicalRecord,
    CanonicalValue,
    SourceReference,
)
from app.canonical.validation import (
    CanonicalStructuralValidator,
    StructuralIssueCode,
)
from tests.canonical_helpers import example_schema, required_values


def validate_records(*records: CanonicalRecord):
    dataset = CanonicalDataset(
        dataset_id="dataset-001", schema=example_schema(), records=list(records)
    )
    return CanonicalStructuralValidator().validate(dataset)


def test_valid_record_is_structurally_valid() -> None:
    result = validate_records(CanonicalRecord(record_id="rec-001", values=required_values()))
    assert result.valid is True
    assert result.issues == []


def test_unknown_field_is_reported() -> None:
    values = required_values()
    values["unknown_field"] = CanonicalValue(
        data_type=CanonicalDataType.STRING, value="synthetic"
    )
    result = validate_records(CanonicalRecord(record_id="rec-001", values=values))

    assert [issue.code for issue in result.issues] == [StructuralIssueCode.UNKNOWN_FIELD]


def test_missing_required_field_is_reported() -> None:
    result = validate_records(
        CanonicalRecord(
            record_id="rec-001",
            values={
                "transaction_date": CanonicalValue(
                    data_type=CanonicalDataType.DATE, value=date(2026, 8, 14)
                )
            },
        )
    )

    assert [issue.code for issue in result.issues] == [
        StructuralIssueCode.MISSING_REQUIRED_FIELD
    ]
    assert result.issues[0].field_id == "quantity"


def test_duplicate_record_ids_are_reported() -> None:
    result = validate_records(
        CanonicalRecord(record_id="rec-001", values=required_values()),
        CanonicalRecord(record_id="rec-001", values=required_values()),
    )
    assert StructuralIssueCode.DUPLICATE_RECORD_ID in {
        issue.code for issue in result.issues
    }


def test_empty_dataset_is_structurally_valid() -> None:
    result = validate_records()
    assert result.valid is True


def test_null_optional_and_required_keys_are_structurally_present() -> None:
    values = required_values()
    values["quantity"] = CanonicalValue(
        data_type=CanonicalDataType.DECIMAL, value=None
    )
    values["description"] = CanonicalValue(
        data_type=CanonicalDataType.STRING, value=None
    )

    result = validate_records(CanonicalRecord(record_id="rec-001", values=values))
    assert result.valid is True


def test_value_type_incompatible_with_schema_is_reported() -> None:
    values = required_values()
    values["quantity"] = CanonicalValue(
        data_type=CanonicalDataType.INTEGER, value=12
    )
    result = validate_records(CanonicalRecord(record_id="rec-001", values=values))

    assert [issue.code for issue in result.issues] == [
        StructuralIssueCode.INVALID_VALUE_TYPE
    ]


def test_invalid_source_reference_is_reported_without_raw_validation_details() -> None:
    invalid_source = SourceReference.model_construct(source_name="example.csv", row=0)
    values = required_values()
    values["quantity"] = CanonicalValue(
        data_type=CanonicalDataType.DECIMAL,
        value=values["quantity"].value,
        source=invalid_source,
    )
    result = validate_records(CanonicalRecord(record_id="rec-001", values=values))

    assert [issue.code for issue in result.issues] == [
        StructuralIssueCode.INVALID_SOURCE_REFERENCE
    ]
