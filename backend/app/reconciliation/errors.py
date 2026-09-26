class ReconciliationError(Exception):
    """Base error for controlled reconciliation failures."""


class ReconciliationRuleSetConfigurationError(ReconciliationError):
    """A reconciliation rule is incompatible with its canonical schema."""
