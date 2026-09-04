"""Participant roles on a hyperedge.

The load-bearing test here is the first one. It asserts both that role names
reach the generated columns and that the positional fallback is *absent*, so it
fails if role naming silently degrades to `user_1_id` / `user_2_id`.
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


def _roled(fixtures_dir):
    return resolve_model(parse_file(fixtures_dir / "roles.hks"))


def test_roles_name_the_generated_columns(fixtures_dir) -> None:
    """The negative control: role names replace the positional suffixes."""
    sql = generate_postgres(_roled(fixtures_dir))

    assert "actor_id" in sql
    assert "target_id" in sql
    assert "venue_id" in sql
    # If role naming falls back to positional suffixes, these reappear.
    assert "user_1_id" not in sql
    assert "user_2_id" not in sql
    assert "UNIQUE (actor_id, target_id, venue_id)" in sql


def test_roles_reach_mongo_and_graphql(fixtures_dir) -> None:
    resolved = _roled(fixtures_dir)

    mongo = generate_mongodb(resolved)
    assert "actor" in mongo and "target" in mongo and "venue" in mongo

    graphql = generate_graphql(resolved)
    assert "actor:" in graphql
    assert "target:" in graphql
    assert "venue:" in graphql


def test_positional_model_is_unchanged(examples_dir) -> None:
    """A model declaring no roles keeps the positional naming it had."""
    sql = generate_postgres(resolve_model(parse_file(examples_dir / "social-network.hks")))

    assert "user_1_id" in sql
    assert "user_2_id" in sql
    assert "group_id" in sql


def test_duplicate_role_in_one_hyperedge_is_refused() -> None:
    source = """
    system S {
        vertices users: User labeled String
        hyperedges pairs: connect actor:User actor:User
    }
    """
    with pytest.raises(ParseError) as caught:
        parse_source(source)
    assert "actor" in str(caught.value)


def test_partly_roled_hyperedge_is_refused() -> None:
    """Roles are all or nothing, so a half-roled edge cannot be read two ways."""
    source = """
    system S {
        vertices users: User labeled String
        vertices groups: Group labeled String
        hyperedges m: connect actor:User Group
    }
    """
    with pytest.raises(ParseError) as caught:
        parse_source(source)
    assert "role" in str(caught.value).lower()


def test_roles_are_recorded_on_the_hyperedge(fixtures_dir) -> None:
    model = parse_file(fixtures_dir / "roles.hks")
    edge = model.hyperedges[0]

    assert edge.connects == ("User", "User", "Group")
    assert edge.roles == ("actor", "target", "venue")
    assert edge.arity == 3
