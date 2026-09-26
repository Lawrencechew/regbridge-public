from decimal import Decimal

import pytest

from app.canonical.builder import CanonicalDatasetBuilder
from app.canonical.errors import CanonicalDatasetError
from app.canonical.models import CanonicalDataType, CanonicalValue, SourceReference
from app.canonical.validation import StructuralIssueCode
from tests.canonical_helpers import example_schema, required_values


def test_builder_adds_record_with_source_provenance() -> None:
    values = required_values()
    values["quantity"] = CanonicalValue(
        data_type=CanonicalDataType.DECIMAL,
        value=Decimal("12.50"),
        source=SourceReference(source_name="example.csv", row=2, column="Amount"),
    )
    dataset = (
        CanonicalDatasetBuilder(example_schema(), "dataset-001")
        .add_record("rec-001", values)
        .build()
    )

    source = dataset.records[0].values["quantity"].source
    assert source is not None
    assert source.row == 2
    assert source.column == "Amount"


def test_builder_rejects_duplicate_record_ids() -> None:
    builder = CanonicalDatasetBuilder(example_schema(), "dataset-001")
    builder.add_record("rec-001", required_values())

    with pytest.raises(CanonicalDatasetError):
        builder.add_record("rec-001", required_values())


def test_builder_rejects_unknown_fields_with_structured_result() -> None:
    values = required_values()
    values["unknown_field"] = CanonicalValue(
        data_type=CanonicalDataType.STRING, value="synthetic"
    )

    with pytest.raises(CanonicalDatasetError) as error:
        CanonicalDatasetBuilder(example_schema(), "dataset-001").add_record(
            "rec-001", values
        )

    assert error.value.result is not None
    assert error.value.result.issues[0].code == StructuralIssueCode.UNKNOWN_FIELD


def test_builder_builds_empty_and_multiple_record_datasets() -> None:
    empty = CanonicalDatasetBuilder(example_schema(), "dataset-empty").build()
    multiple = (
        CanonicalDatasetBuilder(example_schema(), "dataset-many")
        .add_record("rec-001", required_values(Decimal("1.00")))
        .add_record("rec-002", required_values(Decimal("2.00")))
        .build()
    )

    assert empty.records == []
    assert [record.record_id for record in multiple.records] == ["rec-001", "rec-002"]
