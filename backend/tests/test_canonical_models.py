from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.canonical.models import (
    CanonicalDataType,
    CanonicalDataset,
    CanonicalFieldDefinition,
    CanonicalRecord,
    CanonicalSchema,
    CanonicalValue,
    SourceReference,
)
from tests.canonical_helpers import example_schema, required_values


@pytest.mark.parametrize("field_id", ["transaction_date", "quantity_1", "source_party"])
def test_valid_canonical_field_ids(field_id: str) -> None:
    field = CanonicalFieldDefinition(
        id=field_id,
        name="Synthetic Field",
        data_type=CanonicalDataType.STRING,
    )
    assert field.id == field_id


@pytest.mark.parametrize(
    "field_id",
    ["TransactionDate", "transaction-date", "transaction date", "_transaction", "transaction__date"],
)
def test_invalid_canonical_field_ids(field_id: str) -> None:
    with pytest.raises(ValidationError):
        CanonicalFieldDefinition(
            id=field_id,
            name="Synthetic Field",
            data_type=CanonicalDataType.STRING,
        )


@pytest.mark.parametrize(
    ("data_type", "value"),
    [
        (CanonicalDataType.STRING, "synthetic"),
        (CanonicalDataType.INTEGER, 7),
        (CanonicalDataType.DECIMAL, Decimal("12.50")),
        (CanonicalDataType.BOOLEAN, True),
        (CanonicalDataType.DATE, date(2026, 8, 14)),
        (CanonicalDataType.DATETIME, datetime(2026, 8, 14, 9, 30, tzinfo=timezone.utc)),
    ],
)
def test_supported_primitive_types_round_trip_through_json(data_type, value) -> None:
    original = CanonicalValue(data_type=data_type, value=value)
    reconstructed = CanonicalValue.model_validate_json(original.model_dump_json())

    assert reconstructed == original
    assert type(reconstructed.value) is type(value)


def test_decimal_round_trip_is_exact() -> None:
    value = CanonicalValue(
        data_type=CanonicalDataType.DECIMAL,
        value=Decimal("0.1") + Decimal("0.2"),
    )
    reconstructed = CanonicalValue.model_validate_json(value.model_dump_json())

    assert reconstructed.value == Decimal("0.3")
    assert isinstance(reconstructed.value, Decimal)


@pytest.mark.parametrize("row", [0, -1])
def test_source_row_must_be_positive(row: int) -> None:
    with pytest.raises(ValidationError):
        SourceReference(source_name="example.csv", row=row)


@pytest.mark.parametrize("source_name", ["/private/example.csv", "C:\\private\\example.csv"])
def test_source_name_cannot_be_an_absolute_path(source_name: str) -> None:
    with pytest.raises(ValidationError):
        SourceReference(source_name=source_name)


def test_duplicate_schema_fields_are_rejected() -> None:
    field = CanonicalFieldDefinition(
        id="quantity", name="Quantity", data_type=CanonicalDataType.DECIMAL
    )
    with pytest.raises(ValidationError):
        CanonicalSchema(
            id="example-schema",
            version="1.0.0",
            name="Example",
            fields=(field, field),
        )


def test_mapping_aliases_are_trimmed_and_exposed() -> None:
    field = CanonicalFieldDefinition(
        id="company_name",
        name="Company name",
        data_type=CanonicalDataType.STRING,
        aliases=(" Company ", "Licensee"),
    )
    assert field.aliases == ("Company", "Licensee")


@pytest.mark.parametrize("aliases", [("",), ("Company", "company")])
def test_blank_or_duplicate_mapping_aliases_are_rejected(aliases) -> None:
    with pytest.raises(ValidationError):
        CanonicalFieldDefinition(
            id="company_name",
            name="Company name",
            data_type=CanonicalDataType.STRING,
            aliases=aliases,
        )


def test_mapping_terms_cannot_collide_across_schema_fields() -> None:
    with pytest.raises(ValidationError):
        CanonicalSchema(
            id="example-schema",
            version="1.0.0",
            name="Example",
            fields=(
                CanonicalFieldDefinition(
                    id="company_name",
                    name="Company name",
                    data_type=CanonicalDataType.STRING,
                    aliases=("Organisation",),
                ),
                CanonicalFieldDefinition(
                    id="organisation",
                    name="Organisation",
                    data_type=CanonicalDataType.STRING,
                ),
            ),
        )


def test_empty_schema_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CanonicalSchema(
            id="example-schema", version="1.0.0", name="Example", fields=()
        )


def test_invalid_schema_version_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CanonicalSchema(
            id="example-schema",
            version="1.0",
            name="Example",
            fields=(
                CanonicalFieldDefinition(
                    id="description",
                    name="Description",
                    data_type=CanonicalDataType.STRING,
                )
            ),
        )


def test_complete_dataset_round_trips_through_json() -> None:
    dataset = CanonicalDataset(
        dataset_id="dataset-001",
        schema=example_schema(),
        records=[CanonicalRecord(record_id="rec-001", values=required_values())],
        metadata={"source_names": ["example.csv"]},
    )

    reconstructed = CanonicalDataset.model_validate_json(dataset.model_dump_json())

    assert reconstructed == dataset
    assert reconstructed.records[0].values["quantity"].value == Decimal("12.50")


@pytest.mark.parametrize(
    ("data_type", "invalid_value"),
    [
        (CanonicalDataType.STRING, 1),
        (CanonicalDataType.DECIMAL, 1.25),
        (CanonicalDataType.BOOLEAN, 1),
        (CanonicalDataType.BOOLEAN, "false"),
        (CanonicalDataType.INTEGER, True),
        (CanonicalDataType.DATE, datetime(2026, 8, 14, 9, 30)),
        (CanonicalDataType.DATETIME, date(2026, 8, 14)),
    ],
)
def test_canonical_values_do_not_coerce_python_inputs(data_type, invalid_value) -> None:
    with pytest.raises(ValidationError):
        CanonicalValue(data_type=data_type, value=invalid_value)
