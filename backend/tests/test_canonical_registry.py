import pytest

from app.canonical.errors import (
    CanonicalSchemaNotFoundError,
    DuplicateCanonicalSchemaError,
)
from app.canonical.registry import CanonicalSchemaRegistry
from tests.canonical_helpers import example_schema


def test_register_and_retrieve_exact_schema() -> None:
    registry = CanonicalSchemaRegistry()
    schema = example_schema()
    registry.register(schema)

    assert registry.get("example-transactions", "1.0.0") is schema


def test_schema_listing_uses_numeric_version_order() -> None:
    registry = CanonicalSchemaRegistry()
    for version in ["2.0.0", "1.10.0", "1.9.0"]:
        registry.register(example_schema(version))

    assert [schema.version for schema in registry.list_schemas()] == [
        "1.9.0",
        "1.10.0",
        "2.0.0",
    ]


def test_duplicate_schema_version_is_rejected() -> None:
    registry = CanonicalSchemaRegistry()
    registry.register(example_schema())

    with pytest.raises(DuplicateCanonicalSchemaError):
        registry.register(example_schema())


def test_missing_schema_and_version_are_controlled() -> None:
    registry = CanonicalSchemaRegistry()
    registry.register(example_schema())

    with pytest.raises(CanonicalSchemaNotFoundError):
        registry.get("missing-schema", "1.0.0")
    with pytest.raises(CanonicalSchemaNotFoundError):
        registry.get("example-transactions", "2.0.0")
