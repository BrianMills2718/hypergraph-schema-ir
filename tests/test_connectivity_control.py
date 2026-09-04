"""The negative control for the connectivity check.

Two fixtures with known ground truth:

  (a) tests/fixtures/connected.hks  -- provably connected. Every declared vertex
      set participates in at least one hyperedge and all four lie in one
      component.
  (b) tests/fixtures/isolated.hks   -- the minimally-mutated twin of (a). One
      edit: the `group_events` hyperedge is removed, so `events` is provably
      isolated. Nothing else differs.

Every assertion here is on real vertex identity. A test that merely asserted
"the checker returned something" or "the isolated count is an integer" would
pass against the legacy bug, which reports *every* vertex isolated. These
assertions cannot: they pin the exact isolated set, and they require the two
fixtures to disagree.
"""

from __future__ import annotations

from knowledgework import Verdict
from knowledgework import evaluate_constraints
from knowledgework import parse_file
from knowledgework import resolve_model


def _verdict_for(path, constraint: str):
    resolved = resolve_model(parse_file(path))
    verdicts = {v.constraint: v for v in evaluate_constraints(resolved)}
    return resolved, verdicts[constraint]


def test_connected_fixture_holds(fixtures_dir) -> None:
    """Control (a): connected. Isolated set is empty and every vertex has incidence."""
    resolved, verdict = _verdict_for(fixtures_dir / "connected.hks", "connected")

    assert resolved.isolated_instances() == ()
    assert verdict.verdict is Verdict.HOLDS
    assert verdict.declared is True

    # Ground truth, asserted per vertex set by name.
    assert resolved.incidence["users"] == ("friendships", "memberships", "authorship")
    assert resolved.incidence["groups"] == ("memberships", "group_events")
    assert resolved.incidence["posts"] == ("authorship",)
    assert resolved.incidence["events"] == ("group_events",)

    assert [sorted(component) for component in resolved.components()] == [
        ["events", "groups", "posts", "users"]
    ]


def test_isolated_twin_violates(fixtures_dir) -> None:
    """Control (b): exactly one vertex set is isolated, and it is `events`."""
    resolved, verdict = _verdict_for(fixtures_dir / "isolated.hks", "connected")

    # The exact isolated set, not a count. Under the legacy bug this is all four.
    assert resolved.isolated_instances() == ("events",)
    assert verdict.verdict is Verdict.VIOLATED
    assert "events is isolated" in verdict.evidence

    # The other three vertex sets keep their real incidence.
    assert resolved.incidence["users"] == ("friendships", "memberships", "authorship")
    assert resolved.incidence["groups"] == ("memberships",)
    assert resolved.incidence["posts"] == ("authorship",)
    assert resolved.incidence["events"] == ()


def test_control_pair_disagrees(fixtures_dir) -> None:
    """The paired control: the two fixtures must receive different verdicts.

    This is the assertion the legacy implementation fails. It reports both
    fixtures as invalid with all vertices isolated, so the pair agrees, and the
    checker carries no information.
    """
    connected_resolved, connected_verdict = _verdict_for(
        fixtures_dir / "connected.hks", "connected"
    )
    isolated_resolved, isolated_verdict = _verdict_for(
        fixtures_dir / "isolated.hks", "connected"
    )

    assert connected_verdict.verdict is not isolated_verdict.verdict
    assert (connected_verdict.verdict, isolated_verdict.verdict) == (
        Verdict.HOLDS,
        Verdict.VIOLATED,
    )
    assert connected_verdict.passed is True
    assert isolated_verdict.passed is False

    # The twins really are minimal twins: same vertex sets, one hyperedge apart.
    assert connected_resolved.instances == isolated_resolved.instances
    connected_edges = {e.name for e in connected_resolved.model.hyperedges}
    isolated_edges = {e.name for e in isolated_resolved.model.hyperedges}
    assert connected_edges - isolated_edges == {"group_events"}
    assert isolated_edges - connected_edges == set()


def test_twin_difference_is_exactly_one_hyperedge(fixtures_dir) -> None:
    """Guard the control itself: if the fixtures drift apart, this fails."""
    connected = parse_file(fixtures_dir / "connected.hks")
    isolated = parse_file(fixtures_dir / "isolated.hks")

    assert [(v.instance, v.type_name) for v in connected.vertex_sets] == [
        (v.instance, v.type_name) for v in isolated.vertex_sets
    ]
    assert connected.declared_constraint_kinds() == isolated.declared_constraint_kinds() == {
        "connected"
    }
    assert len(connected.hyperedges) - len(isolated.hyperedges) == 1
