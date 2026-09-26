from datetime import date, datetime
from decimal import Decimal

from app.canonical.models import (
    CanonicalDataType,
    CanonicalDataset,
    CanonicalFieldDefinition,
    CanonicalRecord,
    CanonicalSchema,
    CanonicalValue,
)
from app.validation.models import RuleSet, RuleSeverity, ValidationRule


def validation_schema() -> CanonicalSchema:
    fields = (
        ("description", CanonicalDataType.STRING),
        ("quantity", CanonicalDataType.DECIMAL),
        ("status", CanonicalDataType.STRING),
        ("approved", CanonicalDataType.BOOLEAN),
        ("sequence", CanonicalDataType.INTEGER),
        ("transaction_date", CanonicalDataType.DATE),
        ("processed_at", CanonicalDataType.DATETIME),
        ("reference_number", CanonicalDataType.STRING),
    )
    return CanonicalSchema(
        id="example-transactions",
        version="1.0.0",
        name="Synthetic Transactions",
        fields=tuple(
            CanonicalFieldDefinition(
                id=field_id,
                name=field_id.replace("_", " ").title(),
                data_type=data_type,
            )
            for field_id, data_type in fields
        ),
    )


def canonical_value(value, data_type: CanonicalDataType, source=None) -> CanonicalValue:
    return CanonicalValue(data_type=data_type, value=value, source=source)


def dataset(*records: dict[str, CanonicalValue]) -> CanonicalDataset:
    return CanonicalDataset(
        dataset_id="dataset-001",
        schema=validation_schema(),
        records=[
            CanonicalRecord(record_id=f"rec-{index:03d}", values=values)
            for index, values in enumerate(records, start=1)
        ],
    )


def rule_kwargs(
    rule_id: str,
    field_id: str,
    severity: RuleSeverity = RuleSeverity.BLOCKING,
) -> dict:
    return {
        "id": rule_id,
        "name": f"Synthetic {rule_id}",
        "description": "Synthetic non-regulatory test rule.",
        "severity": severity,
        "field_id": field_id,
    }


def rule_set(*rules: ValidationRule) -> RuleSet:
    return RuleSet(
        id="EXAMPLE-RULESET",
        version="1.0.0",
        name="Synthetic RuleSet",
        rules=tuple(rules),
    )


SAMPLE_VALUES = {
    "description": ("Synthetic", CanonicalDataType.STRING),
    "quantity": (Decimal("12.50"), CanonicalDataType.DECIMAL),
    "status": ("active", CanonicalDataType.STRING),
    "approved": (False, CanonicalDataType.BOOLEAN),
    "sequence": (1, CanonicalDataType.INTEGER),
    "transaction_date": (date(2026, 8, 14), CanonicalDataType.DATE),
    "processed_at": (datetime(2026, 8, 14, 9, 30), CanonicalDataType.DATETIME),
    "reference_number": ("REF-001", CanonicalDataType.STRING),
}
