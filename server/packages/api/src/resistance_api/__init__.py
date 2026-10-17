"""HTTP serving layer. Reads analysis artifacts only; never imports the pipeline."""

from .app import create_app

__all__ = ["create_app"]
