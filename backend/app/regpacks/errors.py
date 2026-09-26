class RegPackError(Exception):
    """Base error for predictable RegPack failures."""


class RegPackNotFoundError(RegPackError):
    """A requested pack or version is not installed."""


class RegPackManifestError(RegPackError):
    """A manifest cannot be read or does not match its schema."""


class RegPackComponentError(RegPackError):
    """An executable RegPack component is unsafe or invalid."""


class RegPackVersionError(RegPackError):
    """A pack version is invalid or conflicts with its directory."""


class DuplicateRegPackError(RegPackError):
    """More than one manifest declares the same pack ID and version."""


class RegPackEffectivePeriodError(RegPackError):
    """Effective-version selection is absent or ambiguous."""
