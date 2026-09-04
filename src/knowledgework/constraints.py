"""Four-valued constraint evaluation.

The rule that makes the verdict worth reading: a constraint is reported HOLDS
only when this code actually decided it. Everything else is named. A constraint
that the model did not declare is NOT_APPLICABLE, not passing. A constraint that
cannot be decided from a declaration alone is UNEVALUATED, not passing.

The legacy checker got both wrong in the same function: it reported a
connectivity violation for models that never declared `connected`, and it
reported "valid" for properties it had not computed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .model import ResolvedModel

SUPPORTED_CONSTRAINTS = ("uniform", "directed", "acyclic", "connected")


class Verdict(Enum):
    HOLDS = "holds"
    VIOLATED = "violated"
    UNEVALUATED = "unevaluated"
    NOT_APPLICABLE = "not applicable"


@dataclass(frozen=True)
class ConstraintVerdict:
    """One line of the report."""

    constraint: str
    declared: bool
    verdict: Verdict
    reason: str
    evidence: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        """True only for a constraint this code decided in the affirmative."""
        return self.verdict is Verdict.HOLDS


def _evaluate_uniform(resolved: ResolvedModel, k: int | None) -> tuple[Verdict, str, tuple[str, ...]]:
    if k is None:
        return (
            Verdict.UNEVALUATED,
            "uniform was declared without an arity parameter",
            (),
        )
    if not resolved.model.hyperedges:
        return (
            Verdict.UNEVALUATED,
            "the model declares no hyperedges, so uniformity has nothing to range over",
            (),
        )
    offenders = [
        f"{edge.name} connects {edge.arity} vertex types"
        for edge in resolved.model.hyperedges
        if edge.arity != k
    ]
    if offenders:
        return (
            Verdict.VIOLATED,
            f"{len(offenders)} of {len(resolved.model.hyperedges)} hyperedges do not connect exactly {k} vertex types",
            tuple(offenders),
        )
    return (
        Verdict.HOLDS,
        f"all {len(resolved.model.hyperedges)} hyperedges connect exactly {k} vertex types",
        (),
    )


def _evaluate_connected(resolved: ResolvedModel) -> tuple[Verdict, str, tuple[str, ...]]:
    isolated = resolved.isolated_instances()
    components = resolved.components()
    if isolated:
        return (
            Verdict.VIOLATED,
            f"{len(isolated)} vertex set(s) participate in no hyperedge",
            tuple(f"{name} is isolated" for name in isolated),
        )
    if len(components) > 1:
        rendered = [
            "component: " + ", ".join(sorted(component)) for component in components
        ]
        return (
            Verdict.VIOLATED,
            f"the model splits into {len(components)} disconnected components",
            tuple(rendered),
        )
    return (
        Verdict.HOLDS,
        f"all {len(resolved.instances)} vertex sets lie in one component",
        (),
    )


def _unevaluated_directed() -> tuple[Verdict, str, tuple[str, ...]]:
    return (
        Verdict.UNEVALUATED,
        "direction is not expressible in this DSL: a hyperedge declares which "
        "vertex types it connects, not which way. No structural predicate exists "
        "to decide this, so it is not reported as passing.",
        (),
    )


def _unevaluated_acyclic() -> tuple[Verdict, str, tuple[str, ...]]:
    return (
        Verdict.UNEVALUATED,
        "acyclicity is a property of instance data, not of the declaration. A "
        "cycle among vertex types does not imply a cycle among rows, and this "
        "slice loads no data.",
        (),
    )


def evaluate_constraints(resolved: ResolvedModel) -> list[ConstraintVerdict]:
    """Return one verdict per supported constraint, declared or not."""
    declared = {c.kind: c for c in resolved.model.constraints}
    verdicts: list[ConstraintVerdict] = []

    for kind in SUPPORTED_CONSTRAINTS:
        constraint = declared.get(kind)
        if constraint is None:
            verdicts.append(
                ConstraintVerdict(
                    constraint=kind,
                    declared=False,
                    verdict=Verdict.NOT_APPLICABLE,
                    reason=f"the model does not declare {kind}; nothing is claimed about it",
                )
            )
            continue

        if kind == "uniform":
            verdict, reason, evidence = _evaluate_uniform(resolved, constraint.parameter("k"))
        elif kind == "connected":
            verdict, reason, evidence = _evaluate_connected(resolved)
        elif kind == "directed":
            verdict, reason, evidence = _unevaluated_directed()
        elif kind == "acyclic":
            verdict, reason, evidence = _unevaluated_acyclic()
        else:  # pragma: no cover - SUPPORTED_CONSTRAINTS is exhaustive above
            raise AssertionError(f"no evaluator for supported constraint {kind!r}")

        verdicts.append(
            ConstraintVerdict(
                constraint=constraint.render(),
                declared=True,
                verdict=verdict,
                reason=reason,
                evidence=evidence,
            )
        )

    return verdicts


def render_verdict_report(resolved: ResolvedModel, verdicts: list[ConstraintVerdict]) -> str:
    """Render the constraint verdict as the block the CLI prints."""
    lines: list[str] = []
    lines.append(f"Constraint verdict for system {resolved.model.name}")
    lines.append("=" * (len(lines[0])))
    lines.append("")

    width = max((len(v.constraint) for v in verdicts), default=10)
    for verdict in verdicts:
        marker = "declared" if verdict.declared else "not declared"
        lines.append(
            f"  {verdict.constraint.ljust(width)}  {verdict.verdict.value.upper():<14} ({marker})"
        )
        lines.append(f"      {verdict.reason}")
        for item in verdict.evidence:
            lines.append(f"        - {item}")

    declared_verdicts = [v for v in verdicts if v.declared]
    holds = sum(1 for v in declared_verdicts if v.verdict is Verdict.HOLDS)
    violated = sum(1 for v in declared_verdicts if v.verdict is Verdict.VIOLATED)
    unevaluated = sum(1 for v in declared_verdicts if v.verdict is Verdict.UNEVALUATED)
    lines.append("")
    lines.append(
        f"  {len(declared_verdicts)} declared constraint(s): "
        f"{holds} holding, {violated} violated, {unevaluated} unevaluated."
    )
    lines.append(
        "  An unevaluated constraint has not been checked and is not a passing "
        "constraint. A constraint the model does not declare is reported as not "
        "applicable, never as holding."
    )
    return "\n".join(lines)
