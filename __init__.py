"""Top-level package for Annex 4 Parser.

This package provides utilities for monitoring updates to the
European Union's Artificial Intelligence Act and mapping those
changes onto internal documentation. It is intended to serve
as the entry point for a compliance automation service. At a
high level the parser periodically checks official regulatory
sources for changes, extracts the impacted provisions, and
notifies downstream systems that a review may be necessary.

To get started see :mod:`annex4parser.regulation_monitor`.
"""

# Expose the RegulationMonitor class for convenience
from .regulation_monitor import RegulationMonitor  # noqa: F401
