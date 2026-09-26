from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.core.config import Settings
from app.imports.models import DecimalConversion, FieldMapping, ImportMapping, StringConversion
from app.main import create_app
from app.regpacks.registry import RegPackRegistry


REGPACKS = Path(__file__).parents[2] / "regpacks"
EXAMPLE = Path(__file__).parents[2] / "examples" / "example-evidence.csv"


def test_synthetic_public_demo_pack_loads_with_output() -> None:
    registry = RegPackRegistry(REGPACKS)
    registry.discover()

    pack = registry.get("example-compliance", "1.0.0")

    assert pack.manifest.status == "draft"
    assert pack.regulator.code == "EXAMPLE"
    assert pack.canonical_schema is not None
    assert pack.canonical_schema.id == "example-evidence-record"
    assert pack.validation_rules is not None
    assert pack.reconciliation_rules is not None
    assert pack.output_definition is not None
    assert pack.output_template_path is not None
    assert pack.output_template_path.name == "example-evidence-report.xlsx"
    assert pack.fingerprint is not None and len(pack.fingerprint) == 64


def demo_mapping() -> ImportMapping:
    fields = (
        (1, "organisation_name", StringConversion()),
        (2, "reporting_period", StringConversion()),
        (3, "item_code", StringConversion()),
        (4, "item_description", StringConversion()),
        (5, "unit", StringConversion()),
        (6, "opening_quantity", DecimalConversion()),
        (7, "received_quantity", DecimalConversion()),
        (8, "used_quantity", DecimalConversion()),
        (9, "closing_quantity", DecimalConversion()),
        (10, "notes", StringConversion()),
    )
    return ImportMapping(
        target_schema_id="example-evidence-record",
        target_schema_version="1.0.0",
        fields=tuple(
            FieldMapping(
                source_column_index=index,
                target_field_id=field_id,
                conversion=conversion,
            )
            for index, field_id, conversion in fields
        ),
    )


def test_synthetic_demo_preflights_and_generates_report() -> None:
    settings = Settings(
        _env_file=None,
        regpacks_path=REGPACKS,
        persistence_enabled=False,
    )
    form = {
        "pack_id": "example-compliance",
        "pack_version": "1.0.0",
        "mapping": demo_mapping().model_dump_json(),
    }
    content = EXAMPLE.read_bytes()

    with TestClient(create_app(settings_override=settings)) as client:
        preflight = client.post(
            "/api/v1/regflow/preflight",
            files={"file": ("example-evidence.csv", content, "text/csv")},
            data=form,
        )
        generated = client.post(
            "/api/v1/outputs/generate",
            files={"file": ("example-evidence.csv", content, "text/csv")},
            data=form,
        )

    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["ready"] is True
    assert preflight.json()["can_generate"] is True
    assert generated.status_code == 200, generated.text
    assert len(generated.headers["x-regbridge-artifact-sha256"]) == 64

    workbook = load_workbook(BytesIO(generated.content), read_only=True)
    assert workbook["Summary"]["B3"].value == "Northstar Compliance Labs"
    assert workbook["Evidence"]["A2"].value == "EX-001"
    assert workbook["Evidence"]["G3"].value == 27.25
    workbook.close()
