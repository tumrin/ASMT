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
    """Runtime settings. No clinical thresholds or curated metadata live here."""

    data_dir: Path = field(default_factory=_default_data_dir)
    out_dir: Path = field(default_factory=lambda: Path("output"))

    # Count only the first isolate per patient x species x specimen (surveillance rule).
    surveillance: bool = True

    def to_json(self) -> dict[str, object]:
        return {"surveillance": self.surveillance}
