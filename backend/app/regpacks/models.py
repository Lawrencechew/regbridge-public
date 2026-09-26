from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

from app.regpacks.version import RegPackVersion

if TYPE_CHECKING:
    from pathlib import Path
    from app.canonical.models import CanonicalSchema
    from app.outputs.models import OutputDefinition
    from app.reconciliation.models import ReconciliationRuleSet
    from app.validation.models import RuleSet
    from app.regpacks.workflow import LoadedRegPackSection, WorkflowDefinition

PACK_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PackId = Annotated[str, StringConstraints(pattern=PACK_ID_PATTERN.pattern)]


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RegulatorMetadata(ManifestModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)


class EffectivePeriod(ManifestModel):
    from_date: date = Field(alias="from")
    to_date: date | None = Field(default=None, alias="to")

    @model_validator(mode="after")
    def validate_date_order(self) -> "EffectivePeriod":
        if self.to_date is not None and self.to_date < self.from_date:
            raise ValueError("effective.to must be on or after effective.from")
        return self

    def includes(self, value: date) -> bool:
        return self.from_date <= value and (self.to_date is None or value <= self.to_date)


class RegulatorySource(ManifestModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    url: HttpUrl
    reference: str | None = None
    published_date: date | None = None
    checked_at: date
    content_hash: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")


class RegPackComponents(ManifestModel):
    canonical_schema: str | None = None
    validation_rules: str | None = None
    reconciliation_rules: str | None = None
    workflow: str | None = None
    output: str | None = None

    @model_validator(mode="after")
    def validate_relative_paths(self) -> "RegPackComponents":
        from pathlib import PurePosixPath, PureWindowsPath

        for value in (
            *(item for item in (
                self.canonical_schema,
                self.validation_rules,
                self.reconciliation_rules,
                self.workflow,
            ) if item is not None),
            *(() if self.output is None else (self.output,)),
        ):
            posix = PurePosixPath(value)
            windows = PureWindowsPath(value)
            if (
                posix.is_absolute()
                or windows.is_absolute()
                or ".." in posix.parts
                or ".." in windows.parts
            ):
                raise ValueError("RegPack component paths must remain relative to the pack")
        return self


class SubmissionDeadline(ManifestModel):
    type: Literal["day_of_following_period"]
    day: int = Field(ge=1, le=31)


class ReportingFrequency(ManifestModel):
    frequency: Literal["monthly", "semiannual", "on_request"]


class ReportingAssertion(ManifestModel):
    description: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class ReportingMetadata(ManifestModel):
    frequency: Literal["monthly"] | None = None
    submission_deadline: SubmissionDeadline | None = None
    record_period: ReportingFrequency | None = None
    submission: ReportingFrequency | None = None
    exceptions: list[ReportingAssertion] = Field(default_factory=list)
    notes: list[ReportingAssertion] = Field(default_factory=list)


class RegPackManifest(ManifestModel):
    schema_version: Literal["1.0", "1.1", "1.2"]
    id: PackId
    name: str = Field(min_length=1)
    regulator: RegulatorMetadata
    version: str
    effective: EffectivePeriod
    description: str = Field(min_length=1)
    sources: list[RegulatorySource] = Field(min_length=1)
    status: Literal["draft", "verified", "deprecated"] | None = None
    reporting: ReportingMetadata | None = None
    components: RegPackComponents | None = None

    @model_validator(mode="after")
    def validate_pack_version(self) -> "RegPackManifest":
        RegPackVersion.parse(self.version)
        extended = (self.status, self.reporting, self.components)
        if self.schema_version == "1.1" and any(item is None for item in extended):
            raise ValueError("Manifest schema 1.1 requires status, reporting, and components")
        if self.schema_version == "1.0" and any(item is not None for item in extended):
            raise ValueError("Manifest schema 1.0 does not support executable components")
        if self.schema_version == "1.1" and self.components is not None:
            legacy = (
                self.components.canonical_schema,
                self.components.validation_rules,
                self.components.reconciliation_rules,
            )
            if any(item is None for item in legacy) or self.components.workflow is not None:
                raise ValueError("Manifest schema 1.1 requires legacy executable components")
        if self.schema_version == "1.2":
            if self.status is None or self.reporting is None or self.components is None:
                raise ValueError("Manifest schema 1.2 requires status, reporting, and components")
            if self.components.workflow is None:
                raise ValueError("Manifest schema 1.2 requires a workflow component")
            if any(item is not None for item in (
                self.components.canonical_schema,
                self.components.validation_rules,
                self.components.reconciliation_rules,
            )):
                raise ValueError("Manifest schema 1.2 workflow packs cannot declare legacy components")
            if self.reporting.record_period is None or self.reporting.submission is None:
                raise ValueError("Manifest schema 1.2 requires record-period and submission metadata")
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Regulatory source IDs must be unique")
        return self

    @property
    def parsed_version(self) -> RegPackVersion:
        return RegPackVersion.parse(self.version)


@dataclass(frozen=True)
class LoadedRegPack:
    manifest: RegPackManifest
    canonical_schema: CanonicalSchema | None = None
    validation_rules: RuleSet | None = None
    reconciliation_rules: ReconciliationRuleSet | None = None
    output_definition: OutputDefinition | None = None
    output_template_path: Path | None = None
    fingerprint: str | None = None
    workflow_definition: WorkflowDefinition | None = None
    sections: tuple[LoadedRegPackSection, ...] = ()

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def regulator(self) -> RegulatorMetadata:
        return self.manifest.regulator

    @property
    def effective(self) -> EffectivePeriod:
        return self.manifest.effective

    @property
    def parsed_version(self) -> RegPackVersion:
        return self.manifest.parsed_version
