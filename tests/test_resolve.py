"""Resolution tests: the crossing from vertex type to vertex set identity.

These are the tests that directly guard decision 0001. The legacy defect lives
exactly here, and it was silent, so every assertion below is on identity — which
vertex set — not on a count or on the absence of an exception.
"""

from __future__ import annotations

import pytest

from knowledgework import DuplicateVertexTypeError
from knowledgework import UnknownVertexTypeError
from knowledgework import parse_source
from knowledgework import resolve_model
from knowledgework.resolve import build_type_index

SOURCE = """
system Social {
    vertices users: User labeled String
    vertices groups: Group labeled String
    hyperedges friendships: connect User User
    hyperedges memberships: connect User Group
}
constraints { connected }
"""


def test_type_reference_resolves_to_instance() -> None:
    """A hyperedge naming type `User` produces incidence on vertex set `users`.

    Under the legacy bug this assertion fails: `incidence["users"]` is empty
    because the lookup was keyed on the instance name and probed with `User`.
    """
    resolved = resolve_model(parse_source(SOURCE))

    assert resolved.incidence["users"] == ("friendships", "memberships")
    assert resolved.incidence["groups"] == ("memberships",)

    # Endpoints are instance names, in declaration order, repeats preserved.
    assert resolved.endpoints["friendships"] == ("users", "users")
    assert resolved.endpoints["memberships"] == ("users", "groups")


def test_incidence_is_keyed_on_instance_names_only() -> None:
    """No type name ever appears as a key downstream of resolution."""
    resolved = resolve_model(parse_source(SOURCE))
    assert set(resolved.incidence) == {"users", "groups"}
    assert "User" not in resolved.incidence
    assert "Group" not in resolved.incidence


def test_type_index_maps_type_to_instance() -> None:
    index = build_type_index(parse_source(SOURCE))
    assert index == {"User": "users", "Group": "groups"}


def test_unknown_type_raises() -> None:
    """An unresolvable reference stops, rather than recording an isolated vertex.

    The legacy code guarded this with `if vertex in vertex_connections`, which
    turned a total mismatch into a plausible-looking report.
    """
    source = SOURCE.replace(
        "hyperedges memberships: connect User Group",
        "hyperedges memberships: connect User Community",
    )
    with pytest.raises(UnknownVertexTypeError) as caught:
        resolve_model(parse_source(source))

    error = caught.value
    assert error.hyperedge == "memberships"
    assert error.missing_type == "Community"
    assert set(error.declared_types) == {"User", "Group"}
    message = str(error)
    assert "memberships" in message
    assert "Community" in message
    # The error tells the user the way out, at the moment of failure.
    assert "vertices <name>: Community" in message


def test_duplicate_type_raises() -> None:
    """Two vertex sets binding one type is rejected, not fanned out (decision 0001)."""
    source = """
    system Ambiguous {
        vertices admins: User
        vertices guests: User
        hyperedges friendships: connect User User
    }
    """
    with pytest.raises(DuplicateVertexTypeError) as caught:
        resolve_model(parse_source(source))
    assert caught.value.vertex_type == "User"
    assert set(caught.value.instances) == {"admins", "guests"}


def test_ternary_hyperedge_resolves_all_three_endpoints() -> None:
    resolved = resolve_model(
        parse_source(
            """
            system Ternary {
                vertices users: User
                vertices groups: Group
                hyperedges group_interactions: connect User User Group
            }
            """
        )
    )
    assert resolved.endpoints["group_interactions"] == ("users", "users", "groups")
    assert resolved.incidence["users"] == ("group_interactions",)
    assert resolved.incidence["groups"] == ("group_interactions",)
