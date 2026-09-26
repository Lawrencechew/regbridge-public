from __future__ import annotations

import hashlib
import logging
import re
from pathlib import PureWindowsPath
from uuid import uuid4

from app.canonical.fingerprint import dataset_fingerprint
from app.canonical.models import CanonicalDataset
from app.canonical.validation import CanonicalStructuralValidator
from app.outputs.errors import OutputGenerationError
from app.outputs.models import (
    GeneratedArtifact,
    GeneratedOutput,
    OutputGenerationResult,
    OutputIssue,
    OutputIssueCode,
)
from app.outputs.xlsx import XLSX_MEDIA_TYPE, XlsxTemplateGenerator
from app.regpacks.models import LoadedRegPack
from app.regpacks.runner import RegPackRunner
from app.regpacks.workflow_engine import WorkflowRunResult, WorkflowRunner

logger = logging.getLogger(__name__)


class OutputService:
    def __init__(self, max_file_size_bytes: int, runner: RegPackRunner | None = None) -> None:
        self.max_file_size_bytes = max_file_size_bytes
        self.runner = runner or RegPackRunner()
        self.generators = {"xlsx_template": XlsxTemplateGenerator()}
        self.structural_validator = CanonicalStructuralValidator()
        self.workflow_runner = WorkflowRunner()

    def generate(self, pack: LoadedRegPack, dataset: CanonicalDataset) -> GeneratedOutput:
        if pack.output_definition is None or pack.output_template_path is None:
            return self._failure(OutputIssueCode.OUTPUT_NOT_CONFIGURED, "The selected RegPack has no output definition.")
        if pack.canonical_schema is None or (
            dataset.canonical_schema.id != pack.canonical_schema.id
            or dataset.canonical_schema.version != pack.canonical_schema.version
        ):
            return self._failure(OutputIssueCode.OUTPUT_SCHEMA_MISMATCH, "The canonical dataset schema does not match the selected RegPack.")
        structural = self.structural_validator.validate(dataset)
        if not structural.valid:
            return self._failure(OutputIssueCode.OUTPUT_STRUCTURAL_VALIDATION_FAILED, "The canonical dataset failed structural validation.")
        run = self.runner.run(pack, dataset)
        if not run.validation_report.valid or not run.validation_report.ready:
            return self._failure(
                OutputIssueCode.OUTPUT_BLOCKED_BY_VALIDATION,
                "Blocking validation findings prevent output generation.",
                validation=run.validation_report,
                reconciliation=run.reconciliation_report,
            )
        if not run.reconciliation_report.valid or not run.reconciliation_report.ready:
            return self._failure(
                OutputIssueCode.OUTPUT_BLOCKED_BY_RECONCILIATION,
                "Blocking reconciliation findings prevent output generation.",
                validation=run.validation_report,
                reconciliation=run.reconciliation_report,
            )
        generator = self.generators.get(pack.output_definition.type.value)
        if generator is None:
            return self._failure(OutputIssueCode.OUTPUT_NOT_CONFIGURED, "The configured output type is unsupported.")
        try:
            content = generator.generate(
                dataset,
                pack.output_definition,
                pack.output_template_path,
                self.max_file_size_bytes,
            )
            filename = safe_filename(
                pack.output_definition.filename.pattern,
                pack_id=pack.id,
                pack_version=pack.version,
                dataset_id=dataset.dataset_id,
            )
        except OutputGenerationError as exc:
            return self._failure(
                exc.code,
                exc.message,
                validation=run.validation_report,
                reconciliation=run.reconciliation_report,
            )
        artifact = GeneratedArtifact(
            artifact_id=str(uuid4()),
            filename=filename,
            media_type=XLSX_MEDIA_TYPE,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            pack_id=pack.id,
            pack_version=pack.version,
            pack_fingerprint=pack.fingerprint,
            dataset_id=dataset.dataset_id,
            dataset_fingerprint=dataset_fingerprint(dataset),
            output_definition_id=pack.output_definition.id,
            output_definition_version=pack.output_definition.version,
        )
        result = OutputGenerationResult(
            success=True,
            artifact=artifact,
            validation_report=run.validation_report,
            reconciliation_report=run.reconciliation_report,
        )
        logger.info(
            "Output generated: pack=%s pack_version=%s records=%d artifact_size=%d",
            pack.id,
            pack.version,
            len(dataset.records),
            len(content),
        )
        return GeneratedOutput(result, content)

    def generate_workflow(
        self,
        pack: LoadedRegPack,
        datasets: dict[str, CanonicalDataset],
        runtime_values: dict[str, object],
        *,
        bundle_id: str,
    ) -> tuple[GeneratedOutput, WorkflowRunResult | None]:
        if pack.output_definition is None or pack.output_template_path is None:
            return self._failure(
                OutputIssueCode.OUTPUT_NOT_CONFIGURED,
                "The selected RegPack has no output definition.",
            ), None
        for dataset in datasets.values():
            if not self.structural_validator.validate(dataset).valid:
                return self._failure(
                    OutputIssueCode.OUTPUT_STRUCTURAL_VALIDATION_FAILED,
                    "A canonical section failed structural validation.",
                ), None
        run = self.workflow_runner.run(
            pack, datasets, runtime_values, bundle_id=bundle_id
        )
        if not run.ready:
            return self._failure(
                OutputIssueCode.OUTPUT_BLOCKED_BY_VALIDATION,
                "Blocking workflow findings prevent output generation.",
            ), run
        generator = self.generators.get(pack.output_definition.type.value)
        if generator is None:
            return self._failure(
                OutputIssueCode.OUTPUT_NOT_CONFIGURED,
                "The configured output type is unsupported.",
            ), run
        try:
            content = generator.generate_bundle(
                datasets,
                pack.output_definition,
                pack.output_template_path,
                self.max_file_size_bytes,
                run.runtime_values,
            )
            filename = safe_filename(
                pack.output_definition.filename.pattern,
                pack_id=pack.id,
                pack_version=pack.version,
                dataset_id=bundle_id,
            )
        except OutputGenerationError as exc:
            return self._failure(exc.code, exc.message), run
        artifact = GeneratedArtifact(
            artifact_id=str(uuid4()),
            filename=filename,
            media_type=XLSX_MEDIA_TYPE,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            pack_id=pack.id,
            pack_version=pack.version,
            pack_fingerprint=pack.fingerprint,
            dataset_id=bundle_id,
            dataset_fingerprint=run.bundle_fingerprint,
            output_definition_id=pack.output_definition.id,
            output_definition_version=pack.output_definition.version,
        )
        logger.info(
            "Workflow output generated: pack=%s sections=%d records=%d artifact_size=%d",
            pack.id,
            len(datasets),
            sum(len(dataset.records) for dataset in datasets.values()),
            len(content),
        )
        return GeneratedOutput(
            OutputGenerationResult(success=True, artifact=artifact), content
        ), run

    @staticmethod
    def _failure(code, message, *, validation=None, reconciliation=None) -> GeneratedOutput:
        return GeneratedOutput(
            OutputGenerationResult(
                success=False,
                validation_report=validation,
                reconciliation_report=reconciliation,
                issues=(OutputIssue(code=code, message=message),),
            )
        )


def safe_filename(pattern: str, *, pack_id: str, pack_version: str, dataset_id: str) -> str:
    try:
        name = pattern.format(
            pack_id=pack_id,
            pack_version=pack_version,
            dataset_id=dataset_id,
        )
    except (KeyError, ValueError) as exc:
        raise OutputGenerationError(OutputIssueCode.OUTPUT_MAPPING_INVALID, "The output filename pattern is invalid.") from exc
    if PureWindowsPath(name).is_absolute() or "/" in name or "\\" in name or ".." in name:
        raise OutputGenerationError(OutputIssueCode.OUTPUT_MAPPING_INVALID, "The output filename is unsafe.")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not name.lower().endswith(".xlsx"):
        raise OutputGenerationError(OutputIssueCode.OUTPUT_MAPPING_INVALID, "The output filename must end in .xlsx.")
    if not name or len(name) > 180:
        raise OutputGenerationError(OutputIssueCode.OUTPUT_MAPPING_INVALID, "The output filename length is invalid.")
    return name
