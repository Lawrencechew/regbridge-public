from datetime import date, datetime
from decimal import Decimal

import pytest

from app.imports.conversion import ConversionFailedError, convert_source_value
from app.imports.models import (
    BooleanConversion,
    DateConversion,
    DateTimeConversion,
    DecimalConversion,
    IntegerConversion,
    StringConversion,
)


def test_string_conversion_preserves_or_trims_explicitly() -> None:
    assert convert_source_value("  value  ", StringConversion()) == "  value  "
    assert convert_source_value(
        "  value  ", StringConversion(trim_whitespace=True)
    ) == "value"
    assert convert_source_value("", StringConversion()) == ""
    assert convert_source_value(None, StringConversion()) is None


@pytest.mark.parametrize("source", [12, "12", 12.0, Decimal("12")])
def test_integer_conversion_accepts_only_exact_integers(source) -> None:
    result = convert_source_value(source, IntegerConversion())
    assert result == 12
    assert type(result) is int


@pytest.mark.parametrize("source", [12.5, True, "abc", "12.0"])
def test_integer_conversion_rejects_non_integral_or_ambiguous_values(source) -> None:
    with pytest.raises(ConversionFailedError):
        convert_source_value(source, IntegerConversion())


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("10.25", Decimal("10.25")),
        (10, Decimal("10")),
        (10.25, Decimal("10.25")),
        (-2, Decimal("-2")),
        (0, Decimal("0")),
    ],
)
def test_decimal_conversion_always_returns_decimal(source, expected) -> None:
    result = convert_source_value(source, DecimalConversion())
    assert result == expected
    assert isinstance(result, Decimal)


def test_decimal_conversion_supports_only_explicit_locale_configuration() -> None:
    conversion = DecimalConversion(thousands_separator=",", decimal_separator=".")
    assert convert_source_value("1,234.50", conversion) == Decimal("1234.50")
    with pytest.raises(ConversionFailedError):
        convert_source_value("not-a-number", conversion)


def test_boolean_conversion_uses_explicit_tokens_without_truthiness() -> None:
    conversion = BooleanConversion(
        true_values=("YES",), false_values=("NO",), case_sensitive=False
    )
    assert convert_source_value("yes", conversion) is True
    assert convert_source_value("NO", conversion) is False
    assert convert_source_value(True, conversion) is True
    for invalid in (1, 0, "Y", "anything"):
        with pytest.raises(ConversionFailedError):
            convert_source_value(invalid, conversion)


def test_date_conversion_accepts_native_or_explicit_format_only() -> None:
    conversion = DateConversion(date_format="%d/%m/%Y")
    assert convert_source_value(date(2026, 8, 14), conversion) == date(2026, 8, 14)
    assert convert_source_value("14/08/2026", conversion) == date(2026, 8, 14)
    with pytest.raises(ConversionFailedError):
        convert_source_value("08/14/2026", conversion)
    with pytest.raises(ConversionFailedError):
        convert_source_value("01/02/2026", DateConversion())


def test_datetime_conversion_accepts_native_or_explicit_format_only() -> None:
    native = datetime(2026, 8, 14, 9, 30)
    conversion = DateTimeConversion(datetime_format="%Y-%m-%d %H:%M")
    assert convert_source_value(native, conversion) == native
    assert convert_source_value("2026-08-14 09:30", conversion) == native
    with pytest.raises(ConversionFailedError):
        convert_source_value("14/08/2026 09:30", conversion)
    with pytest.raises(ConversionFailedError):
        convert_source_value("2026-08-14 09:30", DateTimeConversion())


def test_empty_non_string_source_cell_maps_to_null() -> None:
    assert convert_source_value("", DecimalConversion()) is None
    assert convert_source_value(None, IntegerConversion()) is None
