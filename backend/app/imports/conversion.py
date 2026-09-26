from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.canonical.models import CanonicalDataType
from app.imports.models import (
    BooleanConversion,
    Conversion,
    DateConversion,
    DateTimeConversion,
    DecimalConversion,
    IntegerConversion,
    StringConversion,
)


class ConversionFailedError(ValueError):
    pass


def convert_source_value(value: object | None, conversion: Conversion) -> object | None:
    if value is None:
        return None
    if value == "" and conversion.type != CanonicalDataType.STRING:
        return None
    try:
        if isinstance(conversion, StringConversion):
            return _to_string(value, conversion)
        if isinstance(conversion, IntegerConversion):
            return _to_integer(value)
        if isinstance(conversion, DecimalConversion):
            return _to_decimal(value, conversion)
        if isinstance(conversion, BooleanConversion):
            return _to_boolean(value, conversion)
        if isinstance(conversion, DateConversion):
            return _to_date(value, conversion)
        if isinstance(conversion, DateTimeConversion):
            return _to_datetime(value, conversion)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ConversionFailedError from exc
    raise ConversionFailedError


def _to_string(value: object, conversion: StringConversion) -> str:
    if isinstance(value, (str, int, float, Decimal, bool, date, datetime)):
        result = str(value)
        return result.strip() if conversion.trim_whitespace else result
    raise ConversionFailedError


def _to_integer(value: object) -> int:
    if type(value) is int:
        return value
    if type(value) is float and value.is_integer():
        return int(value)
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if type(value) is str:
        stripped = value.strip()
        if not stripped or any(character in stripped for character in ".eE"):
            raise ConversionFailedError
        return int(stripped, 10)
    raise ConversionFailedError


def _to_decimal(value: object, conversion: DecimalConversion) -> Decimal:
    if isinstance(value, bool):
        raise ConversionFailedError
    if isinstance(value, Decimal):
        return value
    if type(value) in (int, float):
        return Decimal(str(value))
    if type(value) is str:
        normalised = value.strip()
        if conversion.thousands_separator is not None:
            normalised = normalised.replace(conversion.thousands_separator, "")
        if conversion.decimal_separator != ".":
            normalised = normalised.replace(conversion.decimal_separator, ".")
        if not normalised:
            raise ConversionFailedError
        return Decimal(normalised)
    raise ConversionFailedError


def _to_boolean(value: object, conversion: BooleanConversion) -> bool:
    if type(value) is bool:
        return value
    if type(value) is not str:
        raise ConversionFailedError
    normalise = (lambda item: item) if conversion.case_sensitive else str.casefold
    candidate = normalise(value)
    if candidate in {normalise(item) for item in conversion.true_values}:
        return True
    if candidate in {normalise(item) for item in conversion.false_values}:
        return False
    raise ConversionFailedError


def _to_date(value: object, conversion: DateConversion) -> date:
    if type(value) is date:
        return value
    if type(value) is datetime:
        return value.date()
    if type(value) is str and conversion.date_format is not None:
        return datetime.strptime(value, conversion.date_format).date()
    raise ConversionFailedError


def _to_datetime(value: object, conversion: DateTimeConversion) -> datetime:
    if type(value) is datetime:
        return value
    if type(value) is str and conversion.datetime_format is not None:
        return datetime.strptime(value, conversion.datetime_format)
    raise ConversionFailedError
