"""Backend schema generators.

Each generator takes a ResolvedModel and returns text. Nothing here connects to
a database, and nothing here executes what it generates. Output is
deterministic: no timestamps, no random identifiers, so two runs of the same
model produce byte-identical files.
"""

from __future__ import annotations

from ..model import ResolvedModel
from .graphql import generate_graphql
from .mongo import generate_mongodb
from .postgres import generate_postgres

BACKENDS: dict[str, tuple[str, object]] = {
    "postgres": ("schema.sql", generate_postgres),
    "mongodb": ("schema.mongodb.js", generate_mongodb),
    "graphql": ("schema.graphql", generate_graphql),
}


def generate_all(resolved: ResolvedModel) -> dict[str, str]:
    """Return {filename: content} for every backend, in declaration order."""
    return {
        filename: generator(resolved)  # type: ignore[operator]
        for filename, generator in BACKENDS.values()
    }


__all__ = ["BACKENDS", "generate_all", "generate_graphql", "generate_mongodb", "generate_postgres"]
