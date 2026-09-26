from datetime import date
from decimal import Decimal

from app.canonical.models import (
    CanonicalDataType,
    CanonicalFieldDefinition,
    CanonicalSchema,
    CanonicalValue,
)


def example_schema(version: str = "1.0.0") -> CanonicalSchema:
    return CanonicalSchema(
        id="example-transactions",
        version=version,
        name="Synthetic Transactions",
        description="A non-regulatory schema used only in tests.",
        fields=(
            CanonicalFieldDefinition(
                id="transaction_date",
                name="Transaction Date",
                data_type=CanonicalDataType.DATE,
                required=True,
            ),
            CanonicalFieldDefinition(
                id="description",
                name="Description",
                data_type=CanonicalDataType.STRING,
                required=False,
            ),
            CanonicalFieldDefinition(
                id="quantity",
                name="Quantity",
                data_type=CanonicalDataType.DECIMAL,
                required=True,
            ),
            CanonicalFieldDefinition(
                id="approved",
                name="Approved",
                data_type=CanonicalDataType.BOOLEAN,
                required=False,
            ),
            CanonicalFieldDefinition(
                id="sequence",
                name="Sequence",
                data_type=CanonicalDataType.INTEGER,
                required=False,
            ),
        ),
    )


def required_values(quantity: Decimal = Decimal("12.50")) -> dict[str, CanonicalValue]:
    return {
        "transaction_date": CanonicalValue(
            data_type=CanonicalDataType.DATE,
            value=date(2026, 8, 14),
        ),
        "quantity": CanonicalValue(
            data_type=CanonicalDataType.DECIMAL,
            value=quantity,
        ),
    }
