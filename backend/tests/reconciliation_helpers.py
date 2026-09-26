from decimal import Decimal

from app.canonical.models import (
    CanonicalDataType,
    CanonicalDataset,
    CanonicalFieldDefinition,
    CanonicalRecord,
    CanonicalSchema,
    CanonicalValue,
)
from app.reconciliation.models import (
    ArithmeticOperator,
    FieldOperand,
    FieldTerm,
    ReconciliationRule,
    ReconciliationRuleSet,
    RowEquationRule,
)
from app.validation.models import RuleSeverity


def reconciliation_schema() -> CanonicalSchema:
    fields = (
        ("category", CanonicalDataType.STRING),
        ("opening_balance", CanonicalDataType.DECIMAL),
        ("incoming", CanonicalDataType.DECIMAL),
        ("outgoing", CanonicalDataType.DECIMAL),
        ("closing_balance", CanonicalDataType.DECIMAL),
        ("declared_change", CanonicalDataType.DECIMAL),
        ("integer_opening", CanonicalDataType.INTEGER),
        ("integer_incoming", CanonicalDataType.INTEGER),
        ("integer_closing", CanonicalDataType.INTEGER),
        ("approved", CanonicalDataType.BOOLEAN),
    )
    return CanonicalSchema(
        id="example-balances",
        version="1.0.0",
        name="Synthetic Balances",
        fields=tuple(
            CanonicalFieldDefinition(
                id=field_id,
                name=field_id.replace("_", " ").title(),
                data_type=data_type,
            )
            for field_id, data_type in fields
        ),
    )


def value(raw, data_type, source=None) -> CanonicalValue:
    return CanonicalValue(data_type=data_type, value=raw, source=source)


def dataset(*records: dict[str, CanonicalValue]) -> CanonicalDataset:
    return CanonicalDataset(
        dataset_id="dataset-001",
        schema=reconciliation_schema(),
        records=[
            CanonicalRecord(record_id=f"rec-{index:03d}", values=values)
            for index, values in enumerate(records, start=1)
        ],
    )


def rule_kwargs(rule_id="REC-001", severity=RuleSeverity.BLOCKING):
    return {
        "id": rule_id,
        "name": f"Synthetic {rule_id}",
        "description": "Synthetic non-regulatory reconciliation.",
        "severity": severity,
    }


def row_rule(tolerance: Decimal = Decimal("0"), **overrides) -> RowEquationRule:
    values = {
        **rule_kwargs(),
        "left": (
            FieldTerm(field_id="opening_balance", operator=ArithmeticOperator.ADD),
            FieldTerm(field_id="incoming", operator=ArithmeticOperator.ADD),
            FieldTerm(field_id="outgoing", operator=ArithmeticOperator.SUBTRACT),
        ),
        "right": FieldOperand(field_id="closing_balance"),
        "tolerance": tolerance,
    }
    values.update(overrides)
    return RowEquationRule(**values)


def rule_set(*rules: ReconciliationRule, version="1.0.0") -> ReconciliationRuleSet:
    return ReconciliationRuleSet(
        id="EXAMPLE-RECONCILIATION",
        version=version,
        name="Synthetic Reconciliation Rules",
        rules=tuple(rules),
    )


def decimal_record(opening, incoming, outgoing, closing, category=None, declared=None):
    record = {
        "opening_balance": value(Decimal(opening) if opening is not None else None, CanonicalDataType.DECIMAL),
        "incoming": value(Decimal(incoming) if incoming is not None else None, CanonicalDataType.DECIMAL),
        "outgoing": value(Decimal(outgoing) if outgoing is not None else None, CanonicalDataType.DECIMAL),
        "closing_balance": value(Decimal(closing) if closing is not None else None, CanonicalDataType.DECIMAL),
    }
    if category != "missing":
        record["category"] = value(category, CanonicalDataType.STRING)
    if declared is not None:
        record["declared_change"] = value(Decimal(declared), CanonicalDataType.DECIMAL)
    return record
