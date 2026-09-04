"""Parser tests: the two names per vertex declaration, and loud syntax errors."""

from __future__ import annotations

import pytest

from knowledgework import ParseError
from knowledgework import parse_file
from knowledgework import parse_source

MINIMAL = """
system Tiny {
    vertices users: User labeled String
    vertices groups: Group
    hyperedges memberships: connect User Group
}
constraints { uniform(2) }
"""


def test_parses_instance_and_type_names() -> None:
    """`vertices users: User` yields instance `users` and type `User`, distinctly.

    This is the fact the legacy validator lost. If the parser collapsed the two
    names into one field, the whole class of bug would be unfixable downstream.
    """
    model = parse_source(MINIMAL)

    users, groups = model.vertex_sets
    assert users.instance == "users"
    assert users.type_name == "User"
    assert users.label_type == "String"

    assert groups.instance == "groups"
    assert groups.type_name == "Group"
    assert groups.label_type is None

    # The hyperedge stores TYPE names, not instance names.
    (membership,) = model.hyperedges
    assert membership.connects == ("User", "Group")
    assert membership.connects != (users.instance, groups.instance)


def test_hyperedge_arity_above_two_is_preserved() -> None:
    model = parse_source(
        """
        system Ternary {
            vertices users: User
            vertices groups: Group
            hyperedges group_interactions: connect User User Group
        }
        """
    )
    (edge,) = model.hyperedges
    assert edge.connects == ("User", "User", "Group")
    assert edge.arity == 3


def test_operations_parsed_and_ignored(examples_dir) -> None:
    """The operations block parses, names are retained, bodies are not interpreted."""
    model = parse_file(examples_dir / "social-network.hks")

    assert [op.name for op in model.operations] == ["getFriends"]
    # The body is kept as raw text and never turned into behaviour.
    assert "traverse" in model.operations[0].raw_body
    # Nothing about an operation reaches the declared structure.
    assert "getFriends" not in {v.instance for v in model.vertex_sets}
    assert "getFriends" not in {e.name for e in model.hyperedges}


def test_operations_absent_is_fine() -> None:
    assert parse_source(MINIMAL).operations == ()


def test_constraint_parameters_parse() -> None:
    model = parse_source(MINIMAL)
    (constraint,) = model.constraints
    assert constraint.kind == "uniform"
    assert constraint.parameter("k") == 2
    assert constraint.render() == "uniform(2)"


def test_syntax_error_raises_with_line() -> None:
    with pytest.raises(ParseError) as caught:
        parse_source(
            "system Broken {\n"
            "    vertices users: User\n"
            "    hyperedges bad connect User User\n"
            "}\n"
        )
    assert caught.value.line == 3
    assert "line 3" in str(caught.value)


def test_unknown_constraint_raises() -> None:
    with pytest.raises(ParseError) as caught:
        parse_source(MINIMAL.replace("uniform(2)", "planar"))
    assert "planar" in str(caught.value)
    assert "supported" in str(caught.value)


def test_uniform_without_parameter_raises() -> None:
    with pytest.raises(ParseError, match="requires a parameter"):
        parse_source(MINIMAL.replace("uniform(2)", "uniform"))
