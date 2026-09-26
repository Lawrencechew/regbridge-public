from pydantic import BaseModel, ConfigDict, Field

from app.regpacks.models import RegPackComponents, RegPackManifest, RegulatorMetadata
from app.canonical.models import CanonicalSchema
from app.regpacks.workflow import RuntimeFieldDefinition, WorkflowRule


class RegPackSummary(BaseModel):
    id: str
    name: str
    regulator: RegulatorMetadata
    versions: list[str]
    workflow_versions: list[str]
    output_versions: list[str]


class RegPackListResponse(BaseModel):
    packs: list[RegPackSummary]


class RegPackVersionsResponse(BaseModel):
    pack_id: str
    versions: list[str]


class RegPackManifestResponse(RegPackManifest):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    components: RegPackComponents | None = Field(default=None, exclude=True)
    fingerprint: str | None = None
    canonical_schema_id: str | None = None
    canonical_schema_version: str | None = None
    validation_rule_set_id: str | None = None
    validation_rule_set_version: str | None = None
    validation_rule_count: int | None = None
    reconciliation_rule_set_id: str | None = None
    reconciliation_rule_set_version: str | None = None
    reconciliation_rule_count: int | None = None
    output_definition_id: str | None = None
    output_definition_version: str | None = None
    output_type: str | None = None
    output_template_source_id: str | None = None
    output_template_sha256: str | None = None
    workflow_definition_id: str | None = None
    workflow_definition_version: str | None = None
    workflow_section_count: int | None = None
    runtime_field_count: int | None = None


class RegPackWorkflowSectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    id: str
    name: str
    description: str | None
    optional: bool
    canonical_schema: CanonicalSchema = Field(alias="schema")
    reconciliation: str


class RegPackWorkflowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    version: str
    runtime_fields: tuple[RuntimeFieldDefinition, ...]
    rules: tuple[WorkflowRule, ...]
    sections: tuple[RegPackWorkflowSectionResponse, ...]
