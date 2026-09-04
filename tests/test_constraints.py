"""Constraint verdict tests, including the undeclared-is-not-passing rule."""

from __future__ import annotations

from knowledgework import Verdict
from knowledgework import evaluate_constraints
from knowledgework import parse_file
from knowledgework import parse_source
from knowledgework import render_verdict_report
from knowledgework import resolve_model

# Same structure as tests/fixtures/isolated.hks -- `events` is isolated -- but
# with NO `connected` constraint declared.
ISOLATED_WITHOUT_CONNECTED = """
system Undeclared {
    vertices users: User
    vertices groups: Group
    vertices events: Event
    hyperedges memberships: connect User Group
}
constraints { uniform(2) }
"""


def _verdicts(source: str) -> dict[str, object]:
    resolved = resolve_model(parse_source(source))
    return {v.constraint: v for v in evaluate_constraints(resolved)}


def test_undeclared_connected_is_not_applicable() -> None:
    """Isolation is a violation only when `connected` was declared.

    The legacy checker reported INVALID for isolated vertices regardless of
    whether the model claimed connectivity. An undeclared constraint is also not
    a passing constraint, so NOT_APPLICABLE is a distinct third answer.
    """
    resolved = resolve_model(parse_source(ISOLATED_WITHOUT_CONNECTED))
    assert resolved.isolated_instances() == ("events",)  # the isolation is real

    verdict = {v.constraint: v for v in evaluate_constraints(resolved)}["connected"]
    assert verdict.declared is False
    assert verdict.verdict is Verdict.NOT_APPLICABLE
    assert verdict.verdict is not Verdict.VIOLATED
    assert verdict.verdict is not Verdict.HOLDS
    assert verdict.passed is False


def test_declared_connected_on_same_structure_is_violated() -> None:
    """The same structure, with `connected` declared, is a violation."""
    verdicts = _verdicts(ISOLATED_WITHOUT_CONNECTED.replace("uniform(2)", "uniform(2) connected"))
    assert verdicts["connected"].verdict is Verdict.VIOLATED
    assert "events is isolated" in verdicts["connected"].evidence


def test_uniform_violated_by_ternary_hyperedge() -> None:
    verdicts = _verdicts(
        """
        system Ternary {
            vertices users: User
            vertices groups: Group
            hyperedges memberships: connect User Group
            hyperedges group_interactions: connect User User Group
        }
        constraints { uniform(2) }
        """
    )
    verdict = verdicts["uniform(2)"]
    assert verdict.verdict is Verdict.VIOLATED
    assert verdict.evidence == ("group_interactions connects 3 vertex types",)


def test_uniform_holds_when_all_hyperedges_are_binary() -> None:
    verdicts = _verdicts(
        """
        system Binary {
            vertices users: User
            vertices groups: Group
            hyperedges memberships: connect User Group
        }
        constraints { uniform(2) }
        """
    )
    assert verdicts["uniform(2)"].verdict is Verdict.HOLDS


def test_uniform_holds_for_declared_arity_three() -> None:
    verdicts = _verdicts(
        """
        system Uniform3 {
            vertices users: User
            vertices groups: Group
            vertices events: Event
            hyperedges attendance: connect User Group Event
        }
        constraints { uniform(3) }
        """
    )
    assert verdicts["uniform(3)"].verdict is Verdict.HOLDS


def test_directed_is_unevaluated() -> None:
    """`directed` is never reported as holding: no predicate exists for it here."""
    verdicts = _verdicts(
        """
        system Directed {
            vertices users: User
            hyperedges friendships: connect User User
        }
        constraints { directed }
        """
    )
    verdict = verdicts["directed"]
    assert verdict.declared is True
    assert verdict.verdict is Verdict.UNEVALUATED
    assert verdict.passed is False
    assert "not reported as passing" in verdict.reason


def test_acyclic_is_unevaluated() -> None:
    verdicts = _verdicts(
        """
        system Acyclic {
            vertices folders: Folder
            vertices documents: Document
            hyperedges contains: connect Folder Document
        }
        constraints { acyclic }
        """
    )
    assert verdicts["acyclic"].verdict is Verdict.UNEVALUATED
    assert "instance data" in verdicts["acyclic"].reason


def test_every_supported_constraint_gets_a_line() -> None:
    verdicts = _verdicts(ISOLATED_WITHOUT_CONNECTED)
    assert set(verdicts) == {"uniform(2)", "directed", "acyclic", "connected"}


def test_disconnected_components_without_isolation_is_violated() -> None:
    """Two islands, each internally connected, still violate `connected`."""
    verdicts = _verdicts(
        """
        system TwoIslands {
            vertices users: User
            vertices groups: Group
            vertices folders: Folder
            vertices documents: Document
            hyperedges memberships: connect User Group
            hyperedges contains: connect Folder Document
        }
        constraints { connected }
        """
    )
    verdict = verdicts["connected"]
    assert verdict.verdict is Verdict.VIOLATED
    assert "2 disconnected components" in verdict.reason


def test_report_states_all_four_verdicts(examples_dir) -> None:
    resolved = resolve_model(parse_file(examples_dir / "social-network.hks"))
    report = render_verdict_report(resolved, evaluate_constraints(resolved))
    assert "HOLDS" in report
    assert "VIOLATED" in report
    assert "UNEVALUATED" in report
    assert "NOT APPLICABLE" in report
    assert "is not a passing constraint" in report
