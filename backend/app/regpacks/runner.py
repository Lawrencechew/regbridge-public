from pydantic import BaseModel, ConfigDict

from app.canonical.fingerprint import dataset_fingerprint
from app.canonical.models import CanonicalDataset, CanonicalSchema
from app.reconciliation.engine import ReconciliationEngine
from app.reconciliation.models import ReconciliationReport, ReconciliationRuleSet
from app.regpacks.errors import RegPackComponentError
from app.regpacks.models import LoadedRegPack
from app.validation.engine import ValidationEngine
from app.validation.models import RuleSet, ValidationReport


class RegPackRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    pack_id: str
    pack_version: str
    pack_fingerprint: str
    dataset_id: str
    dataset_fingerprint: str
    validation_report: ValidationReport
    reconciliation_report: ReconciliationReport
    ready: bool


class RegPackRunner:
    def __init__(self) -> None:
        self.validation_engine = ValidationEngine()
        self.reconciliation_engine = ReconciliationEngine()

    def run(self, pack: LoadedRegPack, dataset: CanonicalDataset) -> RegPackRunResult:
        if not isinstance(pack.canonical_schema, CanonicalSchema):
            raise RegPackComponentError("The RegPack has no executable canonical schema.")
        if not isinstance(pack.validation_rules, RuleSet) or not isinstance(
            pack.reconciliation_rules, ReconciliationRuleSet
        ):
            raise RegPackComponentError("The RegPack has no executable rules.")
        if (
            dataset.canonical_schema.id != pack.canonical_schema.id
            or dataset.canonical_schema.version != pack.canonical_schema.version
        ):
            raise RegPackComponentError(
                "The canonical dataset schema does not match the RegPack schema."
            )
        if pack.fingerprint is None:
            raise RegPackComponentError("The executable RegPack has no fingerprint.")

        validation_report = self.validation_engine.validate(
            dataset, pack.validation_rules
        )
        reconciliation_report = self.reconciliation_engine.reconcile(
            dataset, pack.reconciliation_rules
        )
        return RegPackRunResult(
            pack_id=pack.id,
            pack_version=pack.version,
            pack_fingerprint=pack.fingerprint,
            dataset_id=dataset.dataset_id,
            dataset_fingerprint=dataset_fingerprint(dataset),
            validation_report=validation_report,
            reconciliation_report=reconciliation_report,
            ready=validation_report.ready and reconciliation_report.ready,
        )
