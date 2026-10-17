from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    env = os.environ.get("RESISTANCE_DATA_DIR")
    if env:
        return Path(env).expanduser()
    for parent in Path(__file__).resolve().parents:
        if (parent / "patients.csv").exists():
            return parent
        if (parent / "data" / "patients.csv").exists():
            return parent / "data"
    return Path.cwd()


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Thresholds are the only configurable cutoffs."""

    data_dir: Path = field(default_factory=_default_data_dir)
    out_dir: Path = field(default_factory=lambda: Path("output"))

    # Count only the first isolate per patient x species x specimen per period.
    surveillance: bool = True

    # A rate is only reported at or above this many counted isolates.
    min_isolates: int = 30
    # Exclusive lower bounds for the traffic light: green above, yellow above.
    green_above: float = 0.80
    yellow_above: float = 0.60

    def to_json(self) -> dict[str, object]:
        return {
            "surveillance": self.surveillance,
            "min_isolates": self.min_isolates,
            "green_above": self.green_above,
            "yellow_above": self.yellow_above,
        }
