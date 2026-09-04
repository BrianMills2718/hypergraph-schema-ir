"""The declared model, exactly as written, plus the resolved structure.

The distinction this module exists to keep is that a vertex declaration carries
two names. ``VertexSet.instance`` is what the modeller called the set of things
(``users``); ``VertexSet.type_name`` is the type those things have (``User``).
Hyperedges reference the *type*. Nothing outside ``resolve.py`` is allowed to
cross between the two.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field


#: Field types a declaration may name. A field naming anything else is refused
#: at parse time. `labeled` predates this and still falls back to TEXT, which is
#: an inconsistency recorded in the roadmap rather than fixed here.
FIELD_TYPES: tuple[str, ...] = ("String", "Path", "Int", "Integer", "UUID")

#: Column names the generators produce for every vertex set, which a declared
#: field may not shadow.
GENERATED_COLUMNS: tuple[str, ...] = ("id", "label")


@dataclass(frozen=True)
class Field:
    """One entry in a vertex set's `{ ... }` block.

    ``optional`` carries the trailing `?`. A field without it is NOT NULL in
    PostgreSQL, required in the MongoDB validator, and non-null in GraphQL.
    """

    name: str
    type_name: str
    optional: bool = False
    line: int = 0


@dataclass(frozen=True)
class VertexSet:
    """One `vertices <instance>: <Type> [labeled <T>] [{ <field>* }]` declaration."""

    instance: str
    type_name: str
    label_type: str | None = None
    fields: tuple[Field, ...] = ()
    line: int = 0


@dataclass(frozen=True)
class Hyperedge:
    """One `hyperedges <name>: connect [<role>:]<Type> ...` declaration.

    ``connects`` holds vertex *type* names, in declaration order, and may repeat
    a type (``connect User User``) or name more than two (``connect User User
    Group``). Arity is len(connects).

    ``roles`` names each participant in the same order, or is empty when the
    declaration is positional. Roles are all or nothing — a half-roled edge is a
    parse error — so ``roles`` is either empty or as long as ``connects``.
    Without roles a repeated type is distinguished only by position.
    """

    name: str
    connects: tuple[str, ...]
    roles: tuple[str, ...] = ()
    symmetric: tuple[str, ...] = ()
    fields: tuple[Field, ...] = ()
    line: int = 0

    @property
    def arity(self) -> int:
        return len(self.connects)

    def role_at(self, index: int) -> str | None:
        """The declared role of one participant, or None when positional."""
        return self.roles[index] if self.roles else None

    def symmetric_columns(self, suffix: str = "_id") -> tuple[str, ...]:
        """Column names of the symmetric role pair, or empty when not declared."""
        return tuple(f"{role}{suffix}" for role in self.symmetric)


@dataclass(frozen=True)
class Constraint:
    """One entry in the `constraints { ... }` block."""

    kind: str
    parameters: tuple[tuple[str, int], ...] = ()
    line: int = 0

    def render(self) -> str:
        if not self.parameters:
            return self.kind
        args = ", ".join(str(value) for _, value in self.parameters)
        return f"{self.kind}({args})"

    def parameter(self, name: str) -> int | None:
        for key, value in self.parameters:
            if key == name:
                return value
        return None


@dataclass(frozen=True)
class Operation:
    """An entry in `operations { ... }`.

    Parsed so a legacy-shaped file loads, then ignored. The body is kept as raw
    text and is never interpreted. See the plan's non-goals.
    """

    name: str
    raw_body: str
    line: int = 0


@dataclass(frozen=True)
class Model:
    """A parsed model. Nothing here is resolved yet."""

    name: str
    vertex_sets: tuple[VertexSet, ...]
    hyperedges: tuple[Hyperedge, ...]
    constraints: tuple[Constraint, ...]
    operations: tuple[Operation, ...] = ()

    def declared_constraint_kinds(self) -> set[str]:
        return {c.kind for c in self.constraints}


@dataclass(frozen=True)
class ResolvedModel:
    """A model whose hyperedge type references have been resolved to vertex sets.

    ``incidence`` is keyed on *instance* names — the only keys any downstream
    consumer sees — and maps each vertex set to the names of the hyperedges it
    participates in. ``endpoints`` maps each hyperedge to the vertex-set
    instance names it connects, in declaration order, repeats preserved.
    """

    model: Model
    incidence: dict[str, tuple[str, ...]] = field(default_factory=dict)
    endpoints: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def instances(self) -> tuple[str, ...]:
        return tuple(v.instance for v in self.model.vertex_sets)

    def vertex_set_for_type(self, type_name: str) -> VertexSet:
        for vertex_set in self.model.vertex_sets:
            if vertex_set.type_name == type_name:
                return vertex_set
        raise KeyError(type_name)

    def isolated_instances(self) -> tuple[str, ...]:
        """Vertex sets participating in no hyperedge, by instance name."""
        return tuple(name for name in self.instances if not self.incidence.get(name))

    def components(self) -> list[set[str]]:
        """Connected components over the vertex-set/hyperedge incidence graph."""
        seen: set[str] = set()
        found: list[set[str]] = []
        for start in self.instances:
            if start in seen:
                continue
            component: set[str] = set()
            queue = [start]
            while queue:
                current = queue.pop()
                if current in component:
                    continue
                component.add(current)
                for edge_name in self.incidence.get(current, ()):
                    for neighbour in self.endpoints.get(edge_name, ()):
                        if neighbour not in component:
                            queue.append(neighbour)
            seen |= component
            found.append(component)
        return found
