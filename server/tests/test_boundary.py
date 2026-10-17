from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

API_SRC = (
    Path(__file__).resolve().parents[1] / "packages" / "api" / "src" / "resistance_api"
)
PIPELINE_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+resistance_analysis\b", re.MULTILINE
)


def test_api_never_imports_the_analysis_pipeline_statically() -> None:
    offenders = [
        path.relative_to(API_SRC).as_posix()
        for path in sorted(API_SRC.rglob("*.py"))
        if PIPELINE_IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_importing_the_api_does_not_load_the_pipeline() -> None:
    code = (
        "import sys\n"
        "import resistance_api.app\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] == 'resistance_analysis')\n"
        "print(loaded)\n"
        "sys.exit(1 if loaded else 0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
