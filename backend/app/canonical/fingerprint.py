import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.canonical.models import CanonicalDataset


def _serialise_value(value: object) -> str | int | bool | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if type(value) is datetime:
        return value.isoformat()
    if type(value) is date:
        return value.isoformat()
    if type(value) in {str, int, bool}:
        return value
    raise TypeError("Unsupported canonical value type")


def dataset_fingerprint(dataset: CanonicalDataset) -> str:
    fields = dataset.canonical_schema.fields_by_id
    content = {
        "schema": dataset.canonical_schema.model_dump(mode="json"),
        "records": [
            {
                "record_id": record.record_id,
                "values": {
                    field_id: {
                        "type": fields[field_id].data_type.value
                        if field_id in fields
                        else "unknown",
                        "value": _serialise_value(canonical_value.value),
                    }
                    for field_id, canonical_value in sorted(record.values.items())
                },
            }
            for record in dataset.records
        ],
    }
    canonical_json = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical_json).hexdigest()


class CanonicalDatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    schema_id: str
    schema_version: str
    record_count: int
    field_count: int
    fingerprint: str


def summarise_dataset(dataset: CanonicalDataset) -> CanonicalDatasetSummary:
    return CanonicalDatasetSummary(
        dataset_id=dataset.dataset_id,
        schema_id=dataset.canonical_schema.id,
        schema_version=dataset.canonical_schema.version,
        record_count=len(dataset.records),
        field_count=len(dataset.canonical_schema.fields),
        fingerprint=dataset_fingerprint(dataset),
    )
