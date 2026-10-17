from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from .config import Settings


def analysis_main(argv: list[str] | None = None) -> int:
    from .pipeline import run

    parser = argparse.ArgumentParser(prog="resistance-analysis")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("output"))
    args = parser.parse_args(argv)

    updates: dict[str, object] = {"out_dir": Path(args.out)}
    if args.data_dir is not None:
        updates["data_dir"] = Path(args.data_dir)
    settings = replace(Settings(), **updates)
    result = run(settings)
    counts = result.document["metadata"]["counts"]
    print(f"patients:           {counts['patients']}")
    print(f"isolates:           {result.raw.isolates.height}")
    print(f"antibiogram scopes: {len(result.antibiogram.matrix)}")
    print(f"output written to:  {settings.out_dir.resolve()}")
    return 0


def api_main(argv: list[str] | None = None) -> int:
    import uvicorn

    from .api.app import create_app

    parser = argparse.ArgumentParser(prog="resistance-api")
    parser.add_argument("--dataset", type=Path, default=Path("output/dataset.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    app = create_app(dataset_path=args.dataset)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0
