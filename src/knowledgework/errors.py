"""Named failures for the knowledgework pipeline.

Every error in this module exists because the legacy project turned the same
situation into a silent wrong answer. Nothing here is caught and downgraded to a
warning: an input the pipeline cannot resolve stops the pipeline.
"""

from __future__ import annotations


class KnowledgeworkError(Exception):
    """Base class for every failure this package raises deliberately."""


class ParseError(KnowledgeworkError):
    """The source file is not a well-formed model."""

    def __init__(self, message: str, line: int, column: int = 0) -> None:
        self.line = line
        self.column = column
        super().__init__(f"line {line}: {message}")


class UnknownVertexTypeError(KnowledgeworkError):
    """A hyperedge references a vertex type that no vertex declaration binds.

    The legacy validator skipped this case with ``if name in adjacency`` and
    recorded an isolated vertex instead. Here it stops.
    """

    def __init__(self, hyperedge: str, missing_type: str, declared_types: list[str]) -> None:
        self.hyperedge = hyperedge
        self.missing_type = missing_type
        self.declared_types = list(declared_types)
        known = ", ".join(sorted(declared_types)) or "<none>"
        super().__init__(
            f"hyperedge {hyperedge!r} connects vertex type {missing_type!r}, "
            f"which no vertex declaration binds. Declared types: {known}. "
            f"Declare it with `vertices <name>: {missing_type}` or remove the reference."
        )


class DuplicateVertexTypeError(KnowledgeworkError):
    """Two vertex declarations bind the same type name.

    Resolution is a bijection by decision 0001, so this is rejected rather than
    fanned out across both vertex sets.
    """

    def __init__(self, vertex_type: str, instances: list[str]) -> None:
        self.vertex_type = vertex_type
        self.instances = list(instances)
        joined = ", ".join(instances)
        super().__init__(
            f"vertex type {vertex_type!r} is bound by more than one vertex set ({joined}). "
            f"A hyperedge naming {vertex_type!r} would have no single target. "
            f"Give each vertex set a distinct type."
        )


class DuplicateNameError(KnowledgeworkError):
    """Two declarations share one instance name."""

    def __init__(self, kind: str, name: str) -> None:
        super().__init__(f"duplicate {kind} name {name!r}")
