"""One generation assertion per backend, plus determinism."""

from __future__ import annotations

import json
import re

from knowledgework import parse_file
from knowledgework import resolve_model
from knowledgework.backends import generate_all
from knowledgework.backends import generate_graphql
from knowledgework.backends import generate_mongodb
from knowledgework.backends import generate_postgres


def _resolved(examples_dir):
    return resolve_model(parse_file(examples_dir / "social-network.hks"))


def test_postgres_emits_table_per_vertex_set(examples_dir) -> None:
    """Table names come from vertex *instance* names, never from type names."""
    sql = generate_postgres(_resolved(examples_dir))

    assert "CREATE TABLE users (" in sql
    assert "CREATE TABLE groups (" in sql
    assert "CREATE TABLE posts (" in sql
    assert "CREATE TABLE User (" not in sql  # the type name is not a table


def test_postgres_ternary_hyperedge_has_three_foreign_keys(examples_dir) -> None:
    """A hyperedge of arity 3 reaches the relational schema as three foreign keys."""
    sql = generate_postgres(_resolved(examples_dir))
    block = sql.split("CREATE TABLE group_interactions (")[1].split(");")[0]

    references = re.findall(r"(\w+) UUID NOT NULL REFERENCES (\w+)\(id\)", block)
    assert references == [
        ("user_1_id", "users"),
        ("user_2_id", "users"),
        ("group_id", "groups"),
    ]
    # `connect User User` gives two distinguishable columns, not one collapsed one.
    assert "UNIQUE (user_1_id, user_2_id, group_id)" in block


def test_mongo_emits_jsonschema_validator(examples_dir) -> None:
    script = generate_mongodb(_resolved(examples_dir))

    for collection in ("users", "groups", "posts", "group_interactions"):
        assert f'db.createCollection("{collection}"' in script
    assert script.count("$jsonSchema") == 7  # 3 vertex sets + 4 hyperedges

    # The validator body is real JSON, not an illustrative document literal.
    payload = script.split('db.createCollection("users", {')[1].split("validator: ")[1]
    parsed, _ = json.JSONDecoder().raw_decode(payload)
    assert parsed["$jsonSchema"]["properties"]["label"]["bsonType"] == "string"
    assert "label" in parsed["$jsonSchema"]["required"]


def test_graphql_emits_type_per_vertex_set(examples_dir) -> None:
    sdl = generate_graphql(_resolved(examples_dir))

    assert "type User {" in sdl
    assert "type Group {" in sdl
    assert "type Post {" in sdl
    assert "type Query {" in sdl
    # The ternary hyperedge keeps all three endpoints as fields.
    block = sdl.split("type GroupInteractions {")[1].split("}")[0]
    assert "user1: User!" in block
    assert "user2: User!" in block
    assert "group: Group!" in block


def test_no_inferred_columns(examples_dir) -> None:
    """Nothing is guessed from a type name's spelling.

    The legacy generator inferred `name, email, created_at` for any type whose
    name contained "user". Generated schemas here carry only declared structure.
    """
    sql = generate_postgres(_resolved(examples_dir))
    for guessed in ("email", "created_at", "updated_at", "metadata"):
        assert guessed not in sql


def test_output_is_deterministic(examples_dir) -> None:
    """No timestamps or generated identifiers: two runs are byte-identical."""
    first = generate_all(_resolved(examples_dir))
    second = generate_all(_resolved(examples_dir))
    assert first == second
    assert set(first) == {"schema.sql", "schema.mongodb.js", "schema.graphql"}
