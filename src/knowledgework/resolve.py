"""The one place a vertex *type* name is turned into a vertex *set* identity.

This module is the fix for the legacy defect recorded in decision 0001. The
legacy validator built its adjacency map keyed on instance names and then
looked up type names in it behind an `if name in map` guard, so the lookup
never matched, every vertex recorded zero connections, and nothing raised.

Two rules make that class of failure impossible here:

1. The crossing happens exactly once, in `resolve_model`, and it is a lookup in
   an explicitly built type->instance map rather than an incidental membership
   test.
2. A miss raises `UnknownVertexTypeError`. There is no guard that can skip one.
"""

from __future__ import annotations

from .errors import DuplicateVertexTypeError
from .errors import UnknownVertexTypeError
from .model import Model
from .model import ResolvedModel


def build_type_index(model: Model) -> dict[str, str]:
    """Map each declared vertex *type* name to its vertex *set* instance name.

    Raises DuplicateVertexTypeError if two vertex sets bind one type, because a
    hyperedge naming that type would then have no single target (decision 0001).
    """
    index: dict[str, str] = {}
    for vertex_set in model.vertex_sets:
        existing = index.get(vertex_set.type_name)
        if existing is not None:
            raise DuplicateVertexTypeError(
                vertex_set.type_name, [existing, vertex_set.instance]
            )
        index[vertex_set.type_name] = vertex_set.instance
    return index


def resolve_model(model: Model) -> ResolvedModel:
    """Resolve every hyperedge's type references to vertex-set instance names."""
    type_index = build_type_index(model)

    incidence: dict[str, list[str]] = {v.instance: [] for v in model.vertex_sets}
    endpoints: dict[str, tuple[str, ...]] = {}

    for hyperedge in model.hyperedges:
        resolved: list[str] = []
        for type_name in hyperedge.connects:
            instance = type_index.get(type_name)
            if instance is None:
                raise UnknownVertexTypeError(
                    hyperedge.name, type_name, list(type_index.keys())
                )
            resolved.append(instance)
        endpoints[hyperedge.name] = tuple(resolved)
        for instance in dict.fromkeys(resolved):
            incidence[instance].append(hyperedge.name)

    return ResolvedModel(
        model=model,
        incidence={name: tuple(edges) for name, edges in incidence.items()},
        endpoints=endpoints,
    )
