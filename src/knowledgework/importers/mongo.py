"""Recover a model from the MongoDB script this package generated.

Bounded the same way the PostgreSQL reader is: the input is this package's own
output, not arbitrary MongoDB.

MongoDB keeps more in its executable form than PostgreSQL does. An endpoint's
target collection is a `description` string inside the validator rather than a
comment, so a reader restricted to executable JavaScript still recovers it. Type
names are lost in both, for the same reason — they appear only in comments.
"""

from __future__ import annotations

import json
import re

from ..model import Field
from ..model import Hyperedge
from ..model import Model
from ..model import VertexSet
from .postgres import ImportResult
from .postgres import Loss

_BSON_TO_DECLARED = {"string": "String", "int": "Int"}

_SYSTEM_COMMENT = re.compile(r"^//\s*MongoDB schema for system (\w+)")
_VERTEX_COMMENT = re.compile(r"^//\s*vertex set (\w+) \(type (\w+)\)")
_COLLECTION = re.compile(r'db\.createCollection\(\s*"(\w+)"')
_REFERENCE = re.compile(r"reference into collection `(\w+)`")


def _statements(text: str) -> list[str]:
    lines = [line for line in text.splitlines() if not line.strip().startswith("//")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def _validator_json(statement: str) -> dict | None:
    """The validator payload, scanned by brace matching rather than by regex."""
    marker = statement.find("validator:")
    if marker == -1:
        return None
    start = statement.find("{", marker)
    if start == -1:
        return None
    depth = 0
    for index in range(start, len(statement)):
        if statement[index] == "{":
            depth += 1
        elif statement[index] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(statement[start : index + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _split_validator(validator: dict) -> tuple[dict, tuple[str, str] | None]:
    """Return the JSON schema and any symmetric pair carried beside it."""
    if "$jsonSchema" in validator:
        return validator["$jsonSchema"], None
    symmetric: tuple[str, str] | None = None
    schema: dict = {}
    for member in validator.get("$and", []):
        if "$jsonSchema" in member:
            schema = member["$jsonSchema"]
        expression = member.get("$expr", {})
        # Only `$lte` encodes canonical ordering. Anything else is a rule this
        # reader does not claim to understand, so symmetry stays unrecovered.
        if "$lte" in expression:
            left, right = expression["$lte"]
            symmetric = (left.lstrip("$"), right.lstrip("$"))
    return schema, symmetric


def import_mongodb(script: str, read_comments: bool = False) -> ImportResult:
    """Recover a model, reporting everything that did not survive the trip."""
    losses: list[Loss] = []
    declared_types: dict[str, str] = {}
    system_name = "Recovered"
    if read_comments:
        for line in script.splitlines():
            named = _SYSTEM_COMMENT.match(line.strip())
            if named:
                system_name = named.group(1)
            vertex = _VERTEX_COMMENT.match(line.strip())
            if vertex:
                declared_types[vertex.group(1)] = vertex.group(2)

    collections: list[tuple[str, dict, tuple[str, str] | None]] = []
    for statement in _statements(script):
        collapsed = " ".join(statement.split())
        if ".createIndex(" in collapsed:
            continue  # derivable from the collection it indexes
        match = _COLLECTION.search(collapsed)
        if not match:
            losses.append(
                Loss("unrecognised", f"statement not produced by this package: {collapsed[:70]}")
            )
            continue
        validator = _validator_json(statement)
        if validator is None:
            losses.append(Loss("unrecognised", f"collection {match.group(1)}: validator not readable"))
            continue
        schema, symmetric = _split_validator(validator)
        collections.append((match.group(1), schema, symmetric))

    if not read_comments and collections:
        losses.append(
            Loss(
                "unrecoverable",
                "vertex type name: executable JavaScript records the collection name only, "
                "so a placeholder is used for each declared type name",
            )
        )
        losses.append(
            Loss("unrecoverable", "system name: carried in a comment, not in executable JavaScript")
        )
    losses.append(
        Loss(
            "unrecoverable",
            "declared constraints: `translate` evaluates them and emits none into the script",
        )
    )

    vertex_sets: list[VertexSet] = []
    edges: list[tuple[str, dict, tuple[str, str] | None]] = []
    for name, schema, symmetric in collections:
        properties = schema.get("properties", {})
        if "label" not in properties:
            edges.append((name, schema, symmetric))
            continue
        required = set(schema.get("required", []))
        fields = []
        for field_name, spec in properties.items():
            if field_name in ("_id", "label"):
                continue
            declared = _BSON_TO_DECLARED.get(spec.get("bsonType", ""))
            if declared is None:
                losses.append(Loss("unrecognised", f"{name}.{field_name}: bsonType {spec.get('bsonType')!r}"))
                continue
            fields.append(
                Field(name=field_name, type_name=declared, optional=field_name not in required)
            )
        label_declared = _BSON_TO_DECLARED.get(properties["label"].get("bsonType", ""))
        vertex_sets.append(
            VertexSet(
                instance=name,
                type_name=declared_types.get(name) or _placeholder_type(name),
                label_type=label_declared,
                fields=tuple(fields),
            )
        )

    by_instance = {vertex.instance: vertex.type_name for vertex in vertex_sets}
    hyperedges = []
    for name, schema, symmetric in edges:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        roles: list[str] = []
        connects: list[str] = []
        edge_fields: list[Field] = []
        for field_name, spec in properties.items():
            if field_name == "_id":
                continue
            target = _REFERENCE.search(spec.get("description", ""))
            if target:
                roles.append(field_name)
                connects.append(
                    by_instance.get(target.group(1), _placeholder_type(target.group(1)))
                )
                continue
            # No endpoint reference, so this is a declared attribute of the
            # relationship rather than one of its participants.
            declared = _BSON_TO_DECLARED.get(spec.get("bsonType", ""))
            if declared is None:
                losses.append(
                    Loss("unrecognised", f"{name}.{field_name}: bsonType {spec.get('bsonType')!r}")
                )
                continue
            edge_fields.append(
                Field(name=field_name, type_name=declared, optional=field_name not in required)
            )
        hyperedges.append(
            Hyperedge(
                name=name,
                connects=tuple(connects),
                roles=tuple(roles),
                symmetric=symmetric or (),
                fields=tuple(edge_fields),
            )
        )

    model = Model(
        name=system_name,
        vertex_sets=tuple(vertex_sets),
        hyperedges=tuple(hyperedges),
        constraints=(),
    )
    return ImportResult(model=model, losses=tuple(losses))


def _placeholder_type(instance: str) -> str:
    return instance[:1].upper() + instance[1:]
