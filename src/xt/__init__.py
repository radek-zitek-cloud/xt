"""xt: harness-agnostic hierarchical agent teams on top of Herdr."""

from importlib.metadata import PackageNotFoundError, version

# The one source of the version is pyproject.toml; this reads it back from the installed package.
try:
    __version__ = version("xt")
except PackageNotFoundError:
    __version__ = "0+unknown"
