from __future__ import annotations

from collections.abc import Iterable


def age_band_edges(ages: Iterable[int], bands: int = 5) -> tuple[float, ...]:
    """Quantile edges derived from the observed ages."""
    values = sorted(int(age) for age in ages if age is not None)
    if not values or bands < 2:
        return ()
    return tuple(
        float(values[int(len(values) * index / bands)]) for index in range(1, bands)
    )
