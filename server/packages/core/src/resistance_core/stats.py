from __future__ import annotations

import math

Z_975 = 1.959963984540054


def wilson_interval(k: int, n: int, z: float = Z_975) -> tuple[float, float]:
    """Wilson score interval for a proportion of ``k`` successes out of ``n``."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
