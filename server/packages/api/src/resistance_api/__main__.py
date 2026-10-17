from __future__ import annotations

import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    from .app import create_app

    parser = argparse.ArgumentParser(prog="resistance-api")
    parser.add_argument("--dataset", type=Path, default=Path("output/dataset.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    app = create_app(dataset_path=args.dataset)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
