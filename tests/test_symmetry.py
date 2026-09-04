"""Symmetric role pairs on a hyperedge.

The load-bearing test asserts the CHECK is present for a symmetric pair *and*
absent for the ordinary one in the same model, so it fails if the constraint is
emitted unconditionally or not at all.
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


def _sym(fixtures_dir):
    return resolve_model(parse_file(fixtures_dir / "symmetric.hks"))


def test_symmetric_pair_emits_a_canonical_order_check(fixtures_dir) -> None:
    """The negative control: the CHECK is on the symmetric edge and only there."""
    sql = generate_postgres(_sym(fixtures_dir))

    assert "CHECK (a_id <= b_id)" in sql
    # memberships is roled but not symmetric, so it gets no CHECK.
    memberships = sql.split("CREATE TABLE memberships (")[1].split(");")[0]
    assert "CHECK" not in memberships


def test_positional_model_emits_no_check(examples_dir) -> None:
    sql = generate_postgres(resolve_model(parse_file(examples_dir / "social-network.hks")))
    assert "CHECK" not in sql


def test_mongo_enforces_the_pair_with_expr(fixtures_dir) -> None:
    """The negative control: the $expr wrap is on the symmetric collection only."""
    mongo = generate_mongodb(_sym(fixtures_dir))

    friendships = mongo.split('db.createCollection("friendships"')[1].split("});")[0]
    assert '"$and"' in friendships
    assert '"$expr"' in friendships
    assert '"$lte"' in friendships
    assert '"$a"' in friendships and '"$b"' in friendships
    assert "not enforced" not in friendships


def test_mongo_leaves_other_collections_unwrapped(fixtures_dir) -> None:
    mongo = generate_mongodb(_sym(fixtures_dir))

    memberships = mongo.split('db.createCollection("memberships"')[1].split("});")[0]
    assert '"$and"' not in memberships
    assert '"$jsonSchema"' in memberships

    users = mongo.split('db.createCollection("users"')[1].split("});")[0]
    assert '"$and"' not in users


def test_graphql_still_reports_the_rule_unenforced(fixtures_dir) -> None:
    """SDL has no cross-field constraint, so the note stays truthful there."""
    graphql = generate_graphql(_sym(fixtures_dir))
    assert "symmetric" in graphql and "not enforced" in graphql


def test_symmetric_naming_an_undeclared_role_is_refused() -> None:
    source = """
    system S {
        vertices users: User labeled String
        hyperedges f: connect a:User b:User symmetric(a, zzz)
    }
    """
    with pytest.raises(ParseError) as caught:
        parse_source(source)
    assert "zzz" in str(caught.value)


def test_symmetric_naming_one_role_twice_is_refused() -> None:
    source = """
    system S {
        vertices users: User labeled String
        hyperedges f: connect a:User b:User symmetric(a, a)
    }
    """
    with pytest.raises(ParseError) as caught:
        parse_source(source)
    assert "itself" in str(caught.value)


def test_symmetric_on_a_positional_hyperedge_is_refused() -> None:
    source = """
    system S {
        vertices users: User labeled String
        hyperedges f: connect User User symmetric(a, b)
    }
    """
    with pytest.raises(ParseError) as caught:
        parse_source(source)
    assert "role" in str(caught.value).lower()


def test_symmetry_is_recorded_on_the_hyperedge(fixtures_dir) -> None:
    model = parse_file(fixtures_dir / "symmetric.hks")
    friendships = model.hyperedges[0]
    memberships = model.hyperedges[1]

    assert friendships.symmetric == ("a", "b")
    assert memberships.symmetric == ()
