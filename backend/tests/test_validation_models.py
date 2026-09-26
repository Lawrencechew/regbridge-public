import pytest
from pydantic import ValidationError

from app.validation.engine import ValidationEngine
from app.validation.errors import RuleSetConfigurationError
from app.validation.models import (
    MinimumRule,
    NotBlankRule,
    RegexRule,
    RuleSet,
)
from tests.validation_helpers import dataset, rule_kwargs, rule_set


@pytest.mark.parametrize("rule_id", ["RULE-001", "TEST-AMOUNT-001", "EXAMPLE-REQUIRED-001"])
def test_valid_rule_ids(rule_id: str) -> None:
    rule = NotBlankRule(**rule_kwargs(rule_id, "description"))
    assert rule.id == rule_id


@pytest.mark.parametrize("rule_id", ["rule-001", "RULE_001", "RULE 001", "-RULE-001"])
def test_invalid_rule_ids(rule_id: str) -> None:
    with pytest.raises(ValidationError):
        NotBlankRule(**rule_kwargs(rule_id, "description"))


def test_duplicate_rule_ids_are_rejected() -> None:
    rule = NotBlankRule(**rule_kwargs("RULE-001", "description"))
    with pytest.raises(ValidationError):
        rule_set(rule, rule)


def test_invalid_ruleset_version_and_empty_rules_are_rejected() -> None:
    rule = NotBlankRule(**rule_kwargs("RULE-001", "description"))
    with pytest.raises(ValidationError):
        RuleSet(id="EXAMPLE-RULESET", version="1.0", name="Example", rules=(rule,))
    with pytest.raises(ValidationError):
        RuleSet(id="EXAMPLE-RULESET", version="1.0.0", name="Example", rules=())


def test_invalid_regex_is_rejected_at_definition_time() -> None:
    with pytest.raises(ValidationError):
        RegexRule(**rule_kwargs("REGEX-001", "description"), pattern="[")


def test_incompatible_rule_target_is_configuration_error() -> None:
    rule = MinimumRule(**rule_kwargs("MIN-001", "approved"), minimum=0)
    with pytest.raises(RuleSetConfigurationError):
        ValidationEngine().validate(dataset(), rule_set(rule))


def test_unknown_rule_field_is_configuration_error() -> None:
    rule = NotBlankRule(**rule_kwargs("UNKNOWN-001", "unknown_field"))
    with pytest.raises(RuleSetConfigurationError):
        ValidationEngine().validate(dataset(), rule_set(rule))
