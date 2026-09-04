"""Reading generated MongoDB back into a model.

The gate that matters is the last one. A single reader shows a round trip; two
readers that agree show the representation is carrying the model rather than one
backend's habits.
"""

from __future__ import annotations

import pytest

from knowledgework import parse_file
from knowledgework import resolve_model
from knowledgework.backends import generate_mongodb
from knowledgework.backends import generate_postgres
from knowledgework.importers import import_mongodb
from knowledgework.importers import import_postgres


def _strip_comments(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith(("//", "--"))
    )


def _original(fixtures_dir, name):
    return resolve_model(parse_file(fixtures_dir / name))


@pytest.mark.parametrize("fixture", ["roles.hks", "symmetric.hks", "fields.hks"])
def test_tier1_recovers_structure_from_executable_js(fixtures_dir, fixture) -> None:
    original = _original(fixtures_dir, fixture)
    js = generate_mongodb(original)

    recovered = resolve_model(import_mongodb(_strip_comments(js)).model)

    assert recovered.instances == original.instances
    assert recovered.endpoints == original.endpoints


def test_tier1_reports_type_names_as_unrecoverable(fixtures_dir) -> None:
    js = generate_mongodb(_original(fixtures_dir, "roles.hks"))
    result = import_mongodb(_strip_comments(js))

    assert result.losses
    assert any("type name" in loss.detail.lower() for loss in result.losses)


def test_tier2_reemission_is_byte_identical(fixtures_dir) -> None:
    original = _original(fixtures_dir, "roles.hks")
    js = generate_mongodb(original)

    result = import_mongodb(js, read_comments=True)
    assert generate_mongodb(resolve_model(result.model)) == js


def test_both_readers_recover_the_same_model(fixtures_dir) -> None:
    """The point of two backends: independent front ends must agree."""
    original = _original(fixtures_dir, "symmetric.hks")

    from_sql = import_postgres(_strip_comments(generate_postgres(original))).model
    from_js = import_mongodb(_strip_comments(generate_mongodb(original))).model

    assert resolve_model(from_sql).endpoints == resolve_model(from_js).endpoints
    for sql_edge, js_edge in zip(from_sql.hyperedges, from_js.hyperedges, strict=True):
        assert sql_edge.name == js_edge.name
        assert sql_edge.roles == js_edge.roles
        assert sql_edge.symmetric == js_edge.symmetric


def test_an_unrecognised_statement_is_reported(fixtures_dir) -> None:
    js = generate_mongodb(_original(fixtures_dir, "roles.hks"))
    js += '\ndb.users.dropIndex({ label: 1 });\n'

    result = import_mongodb(_strip_comments(js))
    assert any("dropIndex" in loss.detail for loss in result.losses)


def test_removing_the_expr_stops_symmetry_being_recovered(fixtures_dir) -> None:
    """The control: symmetry is recovered from $expr and nowhere else."""
    js = generate_mongodb(_original(fixtures_dir, "symmetric.hks"))

    recovered = import_mongodb(_strip_comments(js)).model
    assert next(h for h in recovered.hyperedges if h.name == "friendships").symmetric == ("a", "b")

    without = js.replace('"$lte"', '"$noop"')
    stripped = import_mongodb(_strip_comments(without)).model
    assert next(h for h in stripped.hyperedges if h.name == "friendships").symmetric == ()
