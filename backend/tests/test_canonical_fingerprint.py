from decimal import Decimal

from app.canonical.fingerprint import dataset_fingerprint, summarise_dataset
from app.canonical.models import CanonicalDataset, CanonicalRecord, SourceReference
from tests.canonical_helpers import example_schema, required_values


def make_dataset(
    *,
    dataset_id: str = "dataset-001",
    quantities: tuple[str, ...] = ("1.00", "2.00"),
) -> CanonicalDataset:
    return CanonicalDataset(
        dataset_id=dataset_id,
        schema=example_schema(),
        records=[
            CanonicalRecord(
                record_id=f"rec-{index}",
                values=required_values(Decimal(quantity)),
            )
            for index, quantity in enumerate(quantities, start=1)
        ],
    )


def test_same_canonical_content_has_same_fingerprint() -> None:
    assert dataset_fingerprint(make_dataset()) == dataset_fingerprint(make_dataset())


def test_changed_value_and_record_order_change_fingerprint() -> None:
    original = make_dataset()
    changed = make_dataset(quantities=("1.00", "3.00"))
    reordered = CanonicalDataset(
        dataset_id=original.dataset_id,
        schema=original.canonical_schema,
        records=list(reversed(original.records)),
    )

    assert dataset_fingerprint(changed) != dataset_fingerprint(original)
    assert dataset_fingerprint(reordered) != dataset_fingerprint(original)


def test_identity_and_provenance_metadata_do_not_change_content_fingerprint() -> None:
    original = make_dataset()
    changed_identity = make_dataset(dataset_id="another-dataset")
    changed_identity.metadata["created_at"] = "2099-01-01T00:00:00Z"
    changed_identity.records[0].values["quantity"].source = SourceReference(
        source_name="renamed-export.csv", row=99, column="Amount"
    )

    assert dataset_fingerprint(changed_identity) == dataset_fingerprint(original)


def test_dataset_summary_does_not_expose_values() -> None:
    dataset = make_dataset()
    summary = summarise_dataset(dataset)

    assert summary.dataset_id == "dataset-001"
    assert summary.schema_id == "example-transactions"
    assert summary.schema_version == "1.0.0"
    assert summary.record_count == 2
    assert summary.field_count == 5
    assert len(summary.fingerprint) == 64
    assert "1.00" not in summary.model_dump_json()
