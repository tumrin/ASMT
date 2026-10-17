from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import polars as pl

from . import build, structure
from .antibiogram import Antibiogram, build_antibiogram
from .config import Settings
from .load import Dataset, load_dataset


@dataclass
class PipelineResult:
    settings: Settings
    raw: Dataset
    contexts: pl.DataFrame
    analytics: pl.DataFrame
    ab_analytics: pl.DataFrame
    antibiogram: Antibiogram
    document: dict[str, Any]


def run(settings: Settings, *, write: bool = True) -> PipelineResult:
    raw = load_dataset(settings.data_dir)

    contexts = build.build_contexts(raw)
    analytics = build.build_analytics(raw, contexts)
    ab_analytics = build.build_susceptibility_analytics(raw, contexts)

    antibiogram = build_antibiogram(
        contexts,
        analytics,
        ab_analytics,
        raw.patients,
        raw.wards,
        raw.antibiotics,
        settings,
    )
    document = structure.build_document(
        raw, contexts, analytics, ab_analytics, antibiogram, settings
    )

    result = PipelineResult(
        settings=settings,
        raw=raw,
        contexts=contexts,
        analytics=analytics,
        ab_analytics=ab_analytics,
        antibiogram=antibiogram,
        document=document,
    )

    if write:
        write_outputs(result)
    return result


def write_outputs(result: PipelineResult) -> None:
    out_dir = result.settings.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dataset.json").write_text(
        json.dumps(result.document, ensure_ascii=False, default=str), encoding="utf-8"
    )


def build_document_only(settings: Settings) -> dict[str, Any]:
    return run(settings, write=False).document


__all__ = ["PipelineResult", "build_document_only", "run", "write_outputs"]
