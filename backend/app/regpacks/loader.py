import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.canonical.models import CanonicalDataType, CanonicalDataset, CanonicalSchema
from app.outputs.models import OutputDefinition
from app.outputs.xlsx import validate_xlsx_definition
from app.reconciliation.engine import ReconciliationEngine
from app.reconciliation.models import ReconciliationRuleSet
from app.regpacks.errors import (
    RegPackComponentError,
    RegPackManifestError,
    RegPackVersionError,
)
from app.regpacks.models import LoadedRegPack, RegPackManifest
from app.regpacks.workflow import LoadedRegPackSection, WorkflowDefinition
from app.validation.engine import ValidationEngine
from app.validation.models import MaximumRule, MinimumRule, RuleSet


class RegPackLoader:
    """Read and validate one manifest without performing discovery."""

    def load(self, manifest_path: Path) -> RegPackManifest:
        try:
            raw_content = manifest_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RegPackManifestError("The RegPack manifest could not be read.") from exc

        try:
            data: Any = yaml.safe_load(raw_content)
        except yaml.YAMLError as exc:
            raise RegPackManifestError("The RegPack manifest contains invalid YAML.") from exc

        if not isinstance(data, dict):
            raise RegPackManifestError("The RegPack manifest must be a YAML mapping.")

        try:
            return RegPackManifest.model_validate(data)
        except RegPackVersionError:
            raise
        except ValidationError as exc:
            version_errors = [error for error in exc.errors() if error["loc"] == ("version",)]
            if version_errors:
                raise RegPackVersionError("The RegPack version is invalid.") from exc
            raise RegPackManifestError("The RegPack manifest does not match a supported schema.") from exc

    def load_pack(self, manifest_path: Path) -> LoadedRegPack:
        manifest = self.load(manifest_path)
        if manifest.components is None:
            return LoadedRegPack(manifest=manifest)

        pack_root = manifest_path.parent.resolve()
        component_paths = manifest.components
        if component_paths.workflow is not None:
            return self._load_workflow_pack(manifest, pack_root)
        if (
            component_paths.canonical_schema is None
            or component_paths.validation_rules is None
            or component_paths.reconciliation_rules is None
        ):
            raise RegPackComponentError("The RegPack executable components are incomplete.")
        schema = self._load_component(
            pack_root, component_paths.canonical_schema, CanonicalSchema
        )
        validation_rules = self._load_component(
            pack_root, component_paths.validation_rules, RuleSet
        )
        validation_rules = self._normalise_yaml_boundaries(schema, validation_rules)
        reconciliation_rules = self._load_component(
            pack_root, component_paths.reconciliation_rules, ReconciliationRuleSet
        )
        output_definition = None
        output_template_path = None
        if component_paths.output is not None:
            output_definition = self._load_component(
                pack_root, component_paths.output, OutputDefinition
            )
            output_source = next(
                (
                    source
                    for source in manifest.sources
                    if source.id == output_definition.template.source_id
                ),
                None,
            )
            if output_source is None or output_source.content_hash != (
                f"sha256:{output_definition.template.sha256}"
            ):
                raise RegPackComponentError(
                    "The output template hash does not match its manifest source."
                )
            output_template_path = validate_xlsx_definition(
                output_definition,
                schema,
                pack_root,
                {source.id for source in manifest.sources},
            )
        dataset = CanonicalDataset(
            dataset_id="regpack-component-validation",
            schema=schema,
            records=[],
        )
        try:
            ValidationEngine.validate_configuration(dataset, validation_rules)
            ReconciliationEngine.validate_configuration(dataset, reconciliation_rules)
        except Exception as exc:
            raise RegPackComponentError(
                "RegPack rules are incompatible with the declared canonical schema."
            ) from exc

        source_ids = {source.id for source in manifest.sources}
        rule_source_refs = [
            reference
            for rule in (*validation_rules.rules, *reconciliation_rules.rules)
            for reference in rule.source_refs
        ]
        if any(not rule.source_refs for rule in (*validation_rules.rules, *reconciliation_rules.rules)):
            raise RegPackComponentError("Production RegPack rules require source references.")
        if any(
            len(rule.source_refs) != len(set(rule.source_refs))
            for rule in (*validation_rules.rules, *reconciliation_rules.rules)
        ):
            raise RegPackComponentError("RegPack rules contain duplicate source references.")
        if not set(rule_source_refs).issubset(source_ids):
            raise RegPackComponentError("RegPack rules contain dangling source references.")

        fingerprint_content = {
            "manifest": manifest.model_dump(mode="json", by_alias=True),
            "canonical_schema": schema.model_dump(mode="json"),
            "validation_rules": validation_rules.model_dump(mode="json"),
            "reconciliation_rules": reconciliation_rules.model_dump(mode="json"),
            "output_definition": (
                output_definition.model_dump(mode="json")
                if output_definition is not None
                else None
            ),
        }
        encoded = json.dumps(
            fingerprint_content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return LoadedRegPack(
            manifest=manifest,
            canonical_schema=schema,
            validation_rules=validation_rules,
            reconciliation_rules=reconciliation_rules,
            output_definition=output_definition,
            output_template_path=output_template_path,
            fingerprint=hashlib.sha256(encoded).hexdigest(),
        )

    def _load_workflow_pack(
        self, manifest: RegPackManifest, pack_root: Path
    ) -> LoadedRegPack:
        components = manifest.components
        assert components is not None and components.workflow is not None
        workflow = self._load_component(
            pack_root, components.workflow, WorkflowDefinition
        )
        loaded_sections: list[LoadedRegPackSection] = []
        source_ids = {source.id for source in manifest.sources}
        all_rule_refs: list[str] = []
        for definition in workflow.sections:
            schema = self._load_component(
                pack_root, definition.canonical_schema, CanonicalSchema
            )
            rules = self._load_component(
                pack_root, definition.validation_rules, RuleSet
            )
            rules = self._normalise_yaml_boundaries(schema, rules)
            reconciliation = (
                self._load_component(
                    pack_root,
                    definition.reconciliation_rules,
                    ReconciliationRuleSet,
                )
                if definition.reconciliation_rules is not None
                else None
            )
            dataset = CanonicalDataset(
                dataset_id=f"regpack-component-validation-{definition.id}",
                schema=schema,
                records=[],
            )
            try:
                ValidationEngine.validate_configuration(dataset, rules)
                if reconciliation is not None:
                    ReconciliationEngine.validate_configuration(dataset, reconciliation)
            except Exception as exc:
                raise RegPackComponentError(
                    "Workflow rules are incompatible with a declared canonical schema."
                ) from exc
            production_rules = (
                *rules.rules,
                *((reconciliation.rules) if reconciliation is not None else ()),
            )
            if any(not rule.source_refs for rule in production_rules):
                raise RegPackComponentError("Production RegPack rules require source references.")
            all_rule_refs.extend(
                reference for rule in production_rules for reference in rule.source_refs
            )
            loaded_sections.append(
                LoadedRegPackSection(
                    id=definition.id,
                    name=definition.name,
                    description=definition.description,
                    optional=definition.optional,
                    canonical_schema=schema,
                    validation_rules=rules,
                    reconciliation_rules=reconciliation,
                )
            )
        runtime_refs = [
            reference
            for field in workflow.runtime_fields
            for reference in field.source_refs
        ] + [
            reference
            for rule in workflow.rules
            for reference in rule.source_refs
        ]
        reporting_refs = [
            reference
            for assertion in (
                *(manifest.reporting.exceptions if manifest.reporting else ()),
                *(manifest.reporting.notes if manifest.reporting else ()),
            )
            for reference in assertion.source_refs
        ]
        if not set((*all_rule_refs, *runtime_refs, *reporting_refs)).issubset(source_ids):
            raise RegPackComponentError("The RegPack contains dangling source references.")

        output_definition = None
        output_template_path = None
        if components.output is not None:
            output_definition = self._load_component(
                pack_root, components.output, OutputDefinition
            )
            output_source = next(
                (source for source in manifest.sources if source.id == output_definition.template.source_id),
                None,
            )
            if output_source is None or output_source.content_hash != (
                f"sha256:{output_definition.template.sha256}"
            ):
                raise RegPackComponentError(
                    "The output template hash does not match its manifest source."
                )
            if not output_definition.source_refs or not set(output_definition.source_refs).issubset(source_ids):
                raise RegPackComponentError("Workflow output definitions require valid source references.")
            output_template_path = validate_xlsx_definition(
                output_definition,
                {section.id: section.canonical_schema for section in loaded_sections},
                pack_root,
                source_ids,
                runtime_field_ids={field.id for field in workflow.runtime_fields},
            )

        fingerprint_content = {
            "manifest": manifest.model_dump(mode="json", by_alias=True),
            "workflow": workflow.model_dump(mode="json"),
            "sections": [
                {
                    "id": section.id,
                    "schema": section.canonical_schema.model_dump(mode="json"),
                    "validation": section.validation_rules.model_dump(mode="json"),
                    "reconciliation": (
                        section.reconciliation_rules.model_dump(mode="json")
                        if section.reconciliation_rules is not None
                        else None
                    ),
                }
                for section in loaded_sections
            ],
            "output_definition": (
                output_definition.model_dump(mode="json")
                if output_definition is not None
                else None
            ),
        }
        encoded = json.dumps(
            fingerprint_content,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return LoadedRegPack(
            manifest=manifest,
            output_definition=output_definition,
            output_template_path=output_template_path,
            fingerprint=hashlib.sha256(encoded).hexdigest(),
            workflow_definition=workflow,
            sections=tuple(loaded_sections),
        )

    @staticmethod
    def _load_component(pack_root: Path, relative_path: str, model_type):
        candidate = pack_root / relative_path
        if candidate.is_symlink():
            raise RegPackComponentError("RegPack component symlinks are not allowed.")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(pack_root) or not resolved.is_file():
            raise RegPackComponentError("RegPack component path is unsafe or missing.")
        try:
            data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
            return model_type.model_validate(data, strict=False)
        except (OSError, UnicodeError, yaml.YAMLError, ValidationError, ValueError) as exc:
            raise RegPackComponentError("A RegPack component is invalid.") from exc

    @staticmethod
    def _normalise_yaml_boundaries(
        schema: CanonicalSchema, rule_set: RuleSet
    ) -> RuleSet:
        """Recover decimal intent lost by YAML's untyped numeric representation."""
        rules = []
        for rule in rule_set.rules:
            field = schema.fields_by_id.get(rule.field_id)
            if field is not None and field.data_type == CanonicalDataType.DECIMAL:
                if isinstance(rule, MinimumRule):
                    rule = rule.model_copy(
                        update={"minimum": Decimal(str(rule.minimum))}
                    )
                elif isinstance(rule, MaximumRule):
                    rule = rule.model_copy(
                        update={"maximum": Decimal(str(rule.maximum))}
                    )
            rules.append(rule)
        return rule_set.model_copy(update={"rules": tuple(rules)})
