"""Declared fields on a vertex set.

The load-bearing test is the control: a vertex set with no block must still
generate exactly the id and label it did before this slice, so the feature
cannot quietly add columns to models that declared none.
"""

from __future__ import annotations

import pytest

from knowledgework import ParseError
from knowledgework import parse_file
from knowledgework import parse_source
from knowledgework import resolve_model
from knowledgework.backends import generate_graphql
from knowledgework.backends import generate_mongodb
from knowledgework.backends import generate_postgres


def _fields(fixtures_dir):
    return resolve_model(parse_file(fixtures_dir / "fields.hks"))


def _table(sql: str, name: str) -> str:
    return sql.split(f"CREATE TABLE {name} (")[1].split(");")[0]


def test_fields_become_typed_columns(fixtures_dir) -> None:
    users = _table(generate_postgres(_fields(fixtures_dir)), "users")

    assert "email TEXT NOT NULL" in users
    assert "age INTEGER NOT NULL" in users
    # bio is declared `String?`, so it is nullable.
    assert "bio TEXT" in users
    assert "bio TEXT NOT NULL" not in users


def test_a_vertex_set_without_a_block_is_unchanged(fixtures_dir) -> None:
    """The control: declaring no fields must generate no fields."""
    groups = _table(generate_postgres(_fields(fixtures_dir)), "groups")

    assert "id UUID PRIMARY KEY" in groups
    assert "label TEXT NOT NULL UNIQUE" in groups
    assert "email" not in groups
    assert len([line for line in groups.strip().splitlines() if line.strip()]) == 2


def test_fields_carry_nullability_into_mongo(fixtures_dir) -> None:
    mongo = generate_mongodb(_fields(fixtures_dir))
    users = mongo.split('db.createCollection("users"')[1].split("});")[0]

    assert '"email"' in users and '"age"' in users and '"bio"' in users
    required = users.split('"required"')[1].split("]")[0]
    assert '"email"' in required
    assert '"age"' in required
    assert '"bio"' not in required


def test_fields_carry_nullability_into_graphql(fixtures_dir) -> None:
    graphql = generate_graphql(_fields(fixtures_dir))
    user_type = graphql.split("type User {")[1].split("}")[0]

    assert "email: String!" in user_type
    assert "age: Int!" in user_type
    assert "bio: String" in user_type
    assert "bio: String!" not in user_type


def test_duplicate_field_name_is_refused() -> None:
    source = """
    system S {
        vertices users: User labeled String { email: String  email: String }
    }
    """
    with pytest.raises(ParseError) as caught:
        parse_source(source)
    assert "email" in str(caught.value)


def test_a_field_may_not_shadow_a_generated_column() -> None:
    for reserved in ("id", "label"):
        source = f"""
        system S {{
            vertices users: User labeled String {{ {reserved}: String }}
        }}
        """
        with pytest.raises(ParseError) as caught:
            parse_source(source)
        assert reserved in str(caught.value)


def test_unknown_field_type_is_refused() -> None:
    """Silently choosing a column type is the legacy behaviour this repo avoids."""
    source = """
    system S {
        vertices users: User labeled String { email: Wibble }
    }
    """
    with pytest.raises(ParseError) as caught:
        parse_source(source)
    assert "Wibble" in str(caught.value)


def test_fields_are_recorded_on_the_vertex_set(fixtures_dir) -> None:
    model = parse_file(fixtures_dir / "fields.hks")
    users = model.vertex_sets[0]
    groups = model.vertex_sets[1]

    assert [(f.name, f.type_name, f.optional) for f in users.fields] == [
        ("email", "String", False),
        ("age", "Int", False),
        ("bio", "String", True),
    ]
    assert groups.fields == ()


def test_unknown_labeled_type_is_refused() -> None:
    """`labeled` fell back to TEXT while a field with the same type name raised.

    One of the two had to be wrong. Silently choosing a column type is the
    legacy behaviour, so `labeled` is now strict like fields are.
    """
    source = """
    system S {
        vertices users: User labeled Wibble
    }
    """
    with pytest.raises(ParseError) as caught:
        parse_source(source)
    assert "Wibble" in str(caught.value)


def test_known_labeled_types_still_parse() -> None:
    """The control: strictness must not reject the types the emitters map."""
    for declared in ("String", "Path", "Int", "Integer", "UUID"):
        parse_source(f"system S {{ vertices users: User labeled {declared} }}")
