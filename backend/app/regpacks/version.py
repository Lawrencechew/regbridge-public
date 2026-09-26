import re
from dataclasses import dataclass

from app.regpacks.errors import RegPackVersionError

VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


@dataclass(frozen=True, order=True)
class RegPackVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "RegPackVersion":
        if not isinstance(value, str):
            raise RegPackVersionError("RegPack version must be a string.")
        match = VERSION_PATTERN.fullmatch(value)
        if match is None:
            raise RegPackVersionError("RegPack version must use MAJOR.MINOR.PATCH.")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
