"""Shared naming rules for generated schemas.

Every generated name derives from a declared name. Nothing is inferred from a
type name's spelling — the legacy generators guessed columns from substrings
like "user", which puts fields in a schema the model never declared.
"""

from __future__ import annotations

import re

from ..model import Hyperedge
from ..model import ResolvedModel

_LABEL_SQL_TYPES = {
    "String": "TEXT",
    "Path": "TEXT",
    "Int": "INTEGER",
    "Integer": "INTEGER",
    "UUID": "UUID",
}

_LABEL_JSON_TYPES = {
    "String": "string",
    "Path": "string",
    "Int": "int",
    "Integer": "int",
    "UUID": "string",
}

_LABEL_GRAPHQL_TYPES = {
    "String": "String",
    "Path": "String",
    "Int": "Int",
    "Integer": "Int",
    "UUID": "ID",
}


def sql_label_type(label_type: str | None) -> str:
    return _LABEL_SQL_TYPES.get(label_type or "", "TEXT")


def json_label_type(label_type: str | None) -> str:
    return _LABEL_JSON_TYPES.get(label_type or "", "string")


def graphql_label_type(label_type: str | None) -> str:
    return _LABEL_GRAPHQL_TYPES.get(label_type or "", "String")


def pascal_case(name: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", name) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Unnamed"


def camel_case(name: str) -> str:
    pascal = pascal_case(name)
    return pascal[:1].lower() + pascal[1:]


def endpoint_column_names(resolved: ResolvedModel, hyperedge: Hyperedge) -> list[str]:
    """One column name per endpoint, in declaration order.

    A declared role names its own column. Without roles a hyperedge may name the
    same vertex type twice (`connect User User`); those endpoints are distinct
    positions and get positional suffixes, so the join table has two
    distinguishable foreign keys rather than one collapsed column.
    """
    if hyperedge.roles:
        return [f"{role}_id" for role in hyperedge.roles]

    instances = resolved.endpoints[hyperedge.name]
    counts: dict[str, int] = {}
    for instance in instances:
        counts[instance] = counts.get(instance, 0) + 1

    seen: dict[str, int] = {}
    names: list[str] = []
    for instance in instances:
        singular = instance[:-1] if instance.endswith("s") and len(instance) > 1 else instance
        if counts[instance] == 1:
            names.append(f"{singular}_id")
        else:
            seen[instance] = seen.get(instance, 0) + 1
            names.append(f"{singular}_{seen[instance]}_id")
    return names
