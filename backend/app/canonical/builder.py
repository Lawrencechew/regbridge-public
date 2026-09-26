import logging

from app.canonical.errors import CanonicalDatasetError
from app.canonical.models import (
    CanonicalDataset,
    CanonicalRecord,
    CanonicalSchema,
    CanonicalValue,
)
from app.canonical.validation import CanonicalStructuralValidator

logger = logging.getLogger(__name__)


class CanonicalDatasetBuilder:
    def __init__(
        self,
        schema: CanonicalSchema,
        dataset_id: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.schema = schema
        self.dataset_id = dataset_id
        self.metadata = metadata or {}
        self._records: list[CanonicalRecord] = []
        self._record_ids: set[str] = set()
        self._validator = CanonicalStructuralValidator()

    def add_record(
        self, record_id: str, values: dict[str, CanonicalValue]
    ) -> "CanonicalDatasetBuilder":
        if record_id in self._record_ids:
            raise CanonicalDatasetError(f"Record ID '{record_id}' is duplicated.")

        record = CanonicalRecord(record_id=record_id, values=values)
        candidate = CanonicalDataset(
            dataset_id=self.dataset_id,
            schema=self.schema,
            records=[record],
            metadata=self.metadata,
        )
        result = self._validator.validate(candidate)
        if not result.valid:
            raise CanonicalDatasetError(
                "The canonical record is structurally invalid.", result=result
            )

        self._records.append(record)
        self._record_ids.add(record_id)
        return self

    def build(self) -> CanonicalDataset:
        dataset = CanonicalDataset(
            dataset_id=self.dataset_id,
            schema=self.schema,
            records=list(self._records),
            metadata=dict(self.metadata),
        )
        logger.info(
            "Canonical dataset created: schema=%s records=%d",
            self.schema.id,
            len(self._records),
        )
        return dataset
