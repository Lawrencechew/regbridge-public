"""Generic RegPack manifest loading, discovery, and execution."""

__all__ = ["RegPackLoader", "RegPackRegistry", "RegPackRunner"]


def __getattr__(name: str):
    """Keep convenience imports without creating package-import cycles."""
    if name == "RegPackLoader":
        from app.regpacks.loader import RegPackLoader

        return RegPackLoader
    if name == "RegPackRegistry":
        from app.regpacks.registry import RegPackRegistry

        return RegPackRegistry
    if name == "RegPackRunner":
        from app.regpacks.runner import RegPackRunner

        return RegPackRunner
    raise AttributeError(name)
