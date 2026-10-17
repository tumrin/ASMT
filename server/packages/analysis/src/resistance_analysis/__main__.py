from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from .config import Settings


def _build_settings(args: argparse.Namespace) -> Settings:
    settings = Settings()
    updates: dict[str, object] = {
        "out_dir": Path(args.out),
        "surveillance": not args.all_isolates,
    }
    if args.data_dir is not None:
        updates["data_dir"] = Path(args.data_dir)
    return replace(settings, **updates)


def _run(args: argparse.Namespace) -> int:
    from .pipeline import run

    settings = _build_settings(args)
    result = run(settings)
    out = settings.out_dir.resolve()
    counts = result.document["metadata"]["counts"]
    print(f"patients:            {counts['patients']}")
    print(f"isolates:            {result.raw.isolates.height}")
    print(f"deviations detected: {result.deviation_summary['total']}")
    print(f"outliers detected:   {result.outlier_summary['total']}")
    print(f"correlation rows:    {result.correlations.height}")
    print(f"tier lists:          {len(result.tiers)}")
    print(f"output written to:   {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="resistance-analysis")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("output"))
    parser.add_argument(
        "--all-isolates",
        action="store_true",
        help="disable the first-isolate surveillance rule",
    )
    args = parser.parse_args(argv)
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
