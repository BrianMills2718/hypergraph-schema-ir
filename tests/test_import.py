"""Reading generated PostgreSQL back into a model.

Tier 1 reads executable SQL only and must report what it cannot recover. Tier 2
admits the comments and must reproduce the file exactly. The gap between them is
the measured loss, so a test that lets tier 1 quietly reach tier 1 parity would
destroy the point of the slice.
"""

from __future__ import annotations

import re

import pytest

from knowledgework import parse_file
from knowledgework import resolve_model
from knowledgework.backends import generate_postgres
from knowledgework.importers import import_postgres


def _strip_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


def _original(fixtures_dir, name):
    return resolve_model(parse_file(fixtures_dir / name))


@pytest.mark.parametrize("fixture", ["roles.hks", "symmetric.hks", "fields.hks"])
def test_tier1_recovers_structure_from_executable_sql(fixtures_dir, fixture) -> None:
    original = _original(fixtures_dir, fixture)
    sql = generate_postgres(original)

    result = import_postgres(_strip_comments(sql))
    recovered = resolve_model(result.model)

    assert recovered.instances == original.instances
    assert recovered.endpoints == original.endpoints
    for got, want in zip(result.model.hyperedges, original.model.hyperedges, strict=True):
        assert got.name == want.name
        assert got.roles == want.roles
        assert got.symmetric == want.symmetric
    for got, want in zip(result.model.vertex_sets, original.model.vertex_sets, strict=True):
        assert got.instance == want.instance
        assert [(f.name, f.optional) for f in got.fields] == [
            (f.name, f.optional) for f in want.fields
        ]


def test_tier1_reports_type_names_as_unrecoverable(fixtures_dir) -> None:
    """A reader that invents type names must not be able to claim losslessness."""
    sql = generate_postgres(_original(fixtures_dir, "roles.hks"))
    result = import_postgres(_strip_comments(sql))

    assert result.losses, "tier 1 must report what executable SQL cannot carry"
    assert any("type name" in loss.detail.lower() for loss in result.losses)


def test_tier2_reemission_is_byte_identical(fixtures_dir) -> None:
    """Also the first evidence that the generator is deterministic."""
    original = _original(fixtures_dir, "roles.hks")
    sql = generate_postgres(original)

    result = import_postgres(sql, read_comments=True)
    assert generate_postgres(resolve_model(result.model)) == sql


def test_an_unrecognised_statement_is_reported(fixtures_dir) -> None:
    sql = generate_postgres(_original(fixtures_dir, "roles.hks"))
    sql += "\nCREATE TRIGGER audit AFTER INSERT ON users EXECUTE FUNCTION f();\n"

    result = import_postgres(_strip_comments(sql))
    assert any("TRIGGER" in loss.detail for loss in result.losses)


def test_an_unexpected_column_is_reported_not_absorbed(fixtures_dir) -> None:
    sql = generate_postgres(_original(fixtures_dir, "roles.hks"))
    sql = sql.replace(
        "    label TEXT NOT NULL UNIQUE",
        "    label TEXT NOT NULL UNIQUE,\n    surprise GEOMETRY NOT NULL",
        1,
    )
    result = import_postgres(_strip_comments(sql))
    assert any("surprise" in loss.detail for loss in result.losses)


def test_removing_the_check_stops_symmetry_being_recovered(fixtures_dir) -> None:
    """The control: symmetry is recovered from the CHECK and nowhere else."""
    sql = generate_postgres(_original(fixtures_dir, "symmetric.hks"))
    without = re.sub(r",\n    CHECK \([^)]*\)", "", sql)

    recovered = import_postgres(_strip_comments(without)).model
    friendships = next(h for h in recovered.hyperedges if h.name == "friendships")
    assert friendships.symmetric == ()

    still_there = import_postgres(_strip_comments(sql)).model
    assert next(h for h in still_there.hyperedges if h.name == "friendships").symmetric == ("a", "b")


def test_tier2_still_reports_constraints_as_lost(fixtures_dir) -> None:
    """Reading the comments recovers the type names, not the constraints block.

    A report that went silent here would claim a completeness the round trip does
    not have, which is the same defect as calling an unevaluated constraint passing.
    """
    sql = generate_postgres(_original(fixtures_dir, "symmetric.hks"))
    result = import_postgres(sql, read_comments=True)

    assert any("constraint" in loss.detail.lower() for loss in result.losses)


def test_positional_endpoints_are_reported_as_ambiguous(fixtures_dir) -> None:
    """`user_1_id` could be a positional endpoint or a role literally named `user_1`.

    The emitter produces the same column either way, so the reader cannot tell.
    It says so rather than picking one, which is the only honest answer.
    """
    sql = generate_postgres(_original(fixtures_dir, "positional.hks"))
    result = import_postgres(_strip_comments(sql))

    ambiguous = [loss for loss in result.losses if loss.kind == "ambiguous"]
    assert ambiguous, "a positional endpoint must be reported, not silently read as a role"
    assert any("user_1" in loss.detail for loss in ambiguous)


def test_a_roled_model_reports_no_ambiguity(fixtures_dir) -> None:
    """The control: the ambiguity report must not fire on ordinary role names."""
    sql = generate_postgres(_original(fixtures_dir, "roles.hks"))
    result = import_postgres(_strip_comments(sql))

    assert not [loss for loss in result.losses if loss.kind == "ambiguous"]
