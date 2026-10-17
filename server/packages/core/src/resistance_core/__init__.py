"""Shared, dependency-light domain logic used by both the analysis pipeline and the API."""

from .antibiotic_properties import (
    MARKER_FLAGS,
    AntibioticMetadata,
    is_screen,
    marker_codes,
    marker_flags_for,
    metadata_by_code,
    metadata_from_row,
    properties_payload,
)
from .demographics import age_band_edges
from .stats import Z_975, wilson_interval

__all__ = [
    "MARKER_FLAGS",
    "Z_975",
    "AntibioticMetadata",
    "age_band_edges",
    "is_screen",
    "marker_codes",
    "marker_flags_for",
    "metadata_by_code",
    "metadata_from_row",
    "properties_payload",
    "wilson_interval",
]
