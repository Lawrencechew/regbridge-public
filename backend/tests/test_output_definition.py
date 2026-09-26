import pytest
from pydantic import ValidationError

from app.outputs.models import OutputDefinition
from app.outputs.xlsx import validate_xlsx_definition
from app.regpacks.errors import RegPackComponentError
from tests.output_helpers import output_definition, output_schema, write_output_template


def validate(tmp_path, definition):
    return validate_xlsx_definition(definition, output_schema(), tmp_path, {"SRC-001"})


def test_valid_definition_and_template_integrity(tmp_path) -> None:
    template = tmp_path / "template.xlsx"
    digest = write_output_template(template)
    assert validate(tmp_path, output_definition(template, digest)) == template.resolve()


def test_invalid_output_semantic_version(tmp_path) -> None:
    template = tmp_path / "template.xlsx"
    digest = write_output_template(template)
    data = output_definition(template, digest).model_dump(mode="json")
    data["version"] = "one"
    with pytest.raises((ValidationError, ValueError)):
        OutputDefinition.model_validate(data)


@pytest.mark.parametrize("cell", ["A0", "1A", "$A$1", "A-1"])
def test_invalid_cell_coordinate_is_rejected(tmp_path, cell) -> None:
    template = tmp_path / "template.xlsx"
    digest = write_output_template(template)
    data = output_definition(template, digest).model_dump(mode="json")
    data["mappings"][0]["target"]["cell"] = cell
    with pytest.raises(ValidationError):
        OutputDefinition.model_validate(data)


@pytest.mark.parametrize("problem", ["missing", "wrong_hash", "modified"])
def test_missing_or_unverified_template_is_rejected(tmp_path, problem) -> None:
    template = tmp_path / "template.xlsx"
    digest = write_output_template(template)
    definition = output_definition(template, digest)
    if problem == "missing":
        template.unlink()
    elif problem == "wrong_hash":
        definition = definition.model_copy(
            update={"template": definition.template.model_copy(update={"sha256": "0" * 64})}
        )
    else:
        template.write_bytes(template.read_bytes() + b"changed")
    with pytest.raises(RegPackComponentError):
        validate(tmp_path, definition)


def test_unknown_field_and_sheet_are_rejected(tmp_path) -> None:
    template = tmp_path / "template.xlsx"
    digest = write_output_template(template)
    unknown_field = output_definition(template, digest).model_dump(mode="json")
    unknown_field["mappings"][0]["source"]["field_id"] = "missing"
    with pytest.raises(RegPackComponentError):
        validate(tmp_path, OutputDefinition.model_validate(unknown_field, strict=False))
    unknown_sheet = output_definition(template, digest).model_dump(mode="json")
    unknown_sheet["mappings"][0]["target"]["sheet"] = "Missing"
    with pytest.raises(RegPackComponentError):
        validate(tmp_path, OutputDefinition.model_validate(unknown_sheet, strict=False))


@pytest.mark.parametrize("cell", ["B1", "E1"])
def test_formula_or_non_anchor_merged_target_is_rejected(tmp_path, cell) -> None:
    template = tmp_path / "template.xlsx"
    digest = write_output_template(template)
    definition = output_definition(
        template,
        digest,
        mappings=[
            {
                "type": "scalar_cell",
                "source": {"type": "literal", "value": "x"},
                "target": {"sheet": "Summary", "cell": cell},
            }
        ],
    )
    with pytest.raises(RegPackComponentError):
        validate(tmp_path, definition)


def test_duplicate_conflicting_target_is_rejected(tmp_path) -> None:
    template = tmp_path / "template.xlsx"
    digest = write_output_template(template)
    mapping = {
        "type": "scalar_cell",
        "source": {"type": "literal", "value": "x"},
        "target": {"sheet": "Summary", "cell": "C1"},
    }
    with pytest.raises(RegPackComponentError):
        validate(tmp_path, output_definition(template, digest, mappings=[mapping, mapping]))


def test_unsafe_template_path_and_unsupported_type_are_rejected(tmp_path) -> None:
    template = tmp_path / "template.xlsx"
    digest = write_output_template(template)
    definition = output_definition(template, digest)
    unsafe = definition.model_copy(
        update={"template": definition.template.model_copy(update={"local_path": "../template.xlsx"})}
    )
    with pytest.raises(RegPackComponentError):
        validate(tmp_path, unsafe)
    data = definition.model_dump(mode="json")
    data["type"] = "pdf"
    with pytest.raises(ValidationError):
        OutputDefinition.model_validate(data)
