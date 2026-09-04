"""Attributes on a relationship.

The control is the second hyperedge in the fixture: it declares no block and
must emit exactly what it did before this slice, so the feature cannot add
columns to relationships that declared none.
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
from knowledgework.importers import import_mongodb
from knowledgework.importers import import_postgres


def _strip(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith(("//", "--"))
    )


def _model(fixtures_dir):
    return resolve_model(parse_file(fixtures_dir / "edge_fields.hks"))


def test_edge_fields_become_columns(fixtures_dir) -> None:
    sql = generate_postgres(_model(fixtures_dir))
    employment = sql.split("CREATE TABLE employment (")[1].split(");")[0]

    assert "salary INTEGER NOT NULL" in employment
    assert "started TEXT" in employment
    assert "started TEXT NOT NULL" not in employment


def test_a_hyperedge_without_a_block_is_unchanged(fixtures_dir) -> None:
    """The control: declaring no attributes must generate none."""
    sql = generate_postgres(_model(fixtures_dir))
    rivalry = sql.split("CREATE TABLE rivalry (")[1].split(");")[0]

    assert "salary" not in rivalry
    assert "CHECK (a_id <= b_id)" in rivalry
    columns = [line for line in rivalry.strip().splitlines() if line.strip()]
    assert len(columns) == 5  # id, a_id, b_id, UNIQUE, CHECK


def test_edge_fields_reach_mongo_and_graphql(fixtures_dir) -> None:
    resolved = _model(fixtures_dir)

    mongo = generate_mongodb(resolved)
    employment = mongo.split('db.createCollection("employment"')[1].split("});")[0]
    assert '"salary"' in employment
    required = employment.split('"required"')[1].split("]")[0]
    assert '"salary"' in required
    assert '"started"' not in required

    graphql = generate_graphql(resolved)
    employment_type = graphql.split("type Employment {")[1].split("}")[0]
    assert "salary: Int!" in employment_type
    assert "started: String" in employment_type
    assert "started: String!" not in employment_type


def test_both_readers_recover_edge_fields(fixtures_dir) -> None:
    """Adding attributes must not silently break the round trip."""
    original = _model(fixtures_dir)

    from_sql = import_postgres(_strip(generate_postgres(original))).model
    from_js = import_mongodb(_strip(generate_mongodb(original))).model

    for recovered in (from_sql, from_js):
        employment = next(h for h in recovered.hyperedges if h.name == "employment")
        assert [(f.name, f.optional) for f in employment.fields] == [
            ("salary", False),
            ("started", True),
        ]
        rivalry = next(h for h in recovered.hyperedges if h.name == "rivalry")
        assert rivalry.fields == ()
        assert rivalry.symmetric == ("a", "b")


def test_a_duplicate_edge_field_is_refused() -> None:
    source = """
    system S {
        vertices users: User labeled String
        hyperedges pairs: connect a:User b:User { note: String  note: String }
    }
    """
    with pytest.raises(ParseError) as caught:
        parse_source(source)
    assert "note" in str(caught.value)


def test_an_edge_field_may_not_be_called_id() -> None:
    source = """
    system S {
        vertices users: User labeled String
        hyperedges pairs: connect a:User b:User { id: String }
    }
    """
    with pytest.raises(ParseError) as caught:
        parse_source(source)
    assert "id" in str(caught.value)


def test_rendering_shows_recovered_edge_fields(fixtures_dir) -> None:
    """The model kept them; the renderer dropped them.

    A reader that recovers an attribute and a renderer that does not print it
    look exactly like a lossy round trip to anyone reading the output.
    """
    from knowledgework.importers import render_hks

    original = _model(fixtures_dir)
    recovered = import_postgres(_strip(generate_postgres(original))).model
    rendered = render_hks(recovered)

    assert "salary: Int" in rendered
    assert "started: String?" in rendered
