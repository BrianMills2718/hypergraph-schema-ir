"""Recover a model from PostgreSQL this package generated.

Bounded on purpose. The input is the output of `generate_postgres`, not
arbitrary PostgreSQL, which is a far smaller space and enough to measure what a
round trip preserves. Anything the reader does not recognise is reported as a
loss and never skipped: silently absorbing an unread statement is precisely the
failure this repository exists to avoid.

Two tiers, because they support different claims. Reading executable SQL alone
cannot recover a vertex type name — in generated output `User` appears only in
comments — so tier 1 reports that loss rather than inventing a name. Admitting
the comments reaches byte-identical re-emission, but only proves the package can
read its own annotations. The difference between the tiers is the measurement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..model import Field
from ..model import Hyperedge
from ..model import Model
from ..model import VertexSet

#: Reverse of the emitter's declared-to-SQL mapping. It is many-to-one: `String`
#: and `Path` both emit TEXT, so the declared spelling is not recoverable. That
#: costs nothing in re-emission, since both spellings emit the same column.
_SQL_TO_DECLARED = {"TEXT": "String", "INTEGER": "Int", "UUID": "UUID"}

_VERTEX_COMMENT = re.compile(r"^--\s*vertex set (\w+) \(type (\w+)\)")
_SYSTEM_COMMENT = re.compile(r"^--\s*PostgreSQL schema for system (\w+)")
_INLINE_COMMENT = re.compile(r"\s*--.*$")
_CREATE_TABLE = re.compile(r"^CREATE TABLE (\w+) \((.*)\)$", re.DOTALL)
_FK = re.compile(r"^(\w+) UUID NOT NULL REFERENCES (\w+)\(id\) ON DELETE CASCADE$")
_LABEL = re.compile(r"^label (\w+)(?: NOT NULL UNIQUE)?$")
_UNIQUE = re.compile(r"^UNIQUE \((.*)\)$")
_CHECK = re.compile(r"^CHECK \((\w+) <= (\w+)\)$")
_FIELD = re.compile(r"^(\w+) (\w+)(?: (NOT NULL))?$")
_POSITIONAL = re.compile(r"^(.+)_(\d+)$")


@dataclass(frozen=True)
class Loss:
    """One thing the reader could not recover, or did not recognise."""

    kind: str  # "unrecoverable" | "unrecognised" | "ambiguous"
    detail: str


@dataclass(frozen=True)
class ImportResult:
    model: Model
    losses: tuple[Loss, ...]


@dataclass
class _Table:
    name: str
    label_sql: str | None = None
    has_label: bool = False
    fields: list[Field] = None  # type: ignore[assignment]
    foreign_keys: list[tuple[str, str]] = None  # type: ignore[assignment]
    unique: tuple[str, ...] = ()
    check: tuple[str, str] | None = None

    def __post_init__(self) -> None:
        self.fields = self.fields or []
        self.foreign_keys = self.foreign_keys or []

    @property
    def is_hyperedge(self) -> bool:
        """A relationship table is id plus foreign keys, uniquely constrained.

        A vertex table carries a label column and a relationship table never
        does, so within this package's own output the two are distinguishable
        without reading a comment.
        """
        if self.has_label or len(self.foreign_keys) < 2 or not self.unique:
            return False
        return set(self.unique) == {column for column, _ in self.foreign_keys}


def _statements(sql: str) -> list[str]:
    """Statements with every comment removed.

    Comments are stripped per line, before any whitespace collapsing. Collapsing
    first lets a trailing comment swallow the column on the next line, which
    silently drops a field.
    """
    lines = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(_INLINE_COMMENT.sub("", line))
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def import_postgres(sql: str, read_comments: bool = False) -> ImportResult:
    """Recover a model, reporting everything that did not survive the trip."""
    losses: list[Loss] = []

    declared_types: dict[str, str] = {}
    system_name = "Recovered"
    if read_comments:
        for line in sql.splitlines():
            match = _VERTEX_COMMENT.match(line.strip())
            if match:
                declared_types[match.group(1)] = match.group(2)
            named = _SYSTEM_COMMENT.match(line.strip())
            if named:
                system_name = named.group(1)

    tables: list[_Table] = []
    for statement in _statements(sql):
        collapsed = " ".join(statement.split())
        if collapsed.startswith("CREATE EXTENSION"):
            continue
        if collapsed.startswith("CREATE INDEX"):
            continue  # derivable from the table it indexes
        match = _CREATE_TABLE.match(collapsed)
        if not match:
            losses.append(Loss("unrecognised", f"statement not produced by this package: {collapsed[:70]}"))
            continue
        tables.append(_read_table(match.group(1), match.group(2), losses))

    vertex_tables = [table for table in tables if not table.is_hyperedge]
    edge_tables = [table for table in tables if table.is_hyperedge]

    if not read_comments and vertex_tables:
        losses.append(
            Loss(
                "unrecoverable",
                "vertex type name: executable SQL records the table name only, so a "
                "placeholder is used for each declared type name",
            )
        )

    vertex_sets = []
    for table in vertex_tables:
        type_name = declared_types.get(table.name) or _placeholder_type(table.name)
        label_type = _SQL_TO_DECLARED.get(table.label_sql or "") if table.label_sql else None
        vertex_sets.append(
            VertexSet(
                instance=table.name,
                type_name=type_name,
                label_type=label_type,
                fields=tuple(table.fields),
            )
        )

    by_instance = {vertex.instance: vertex.type_name for vertex in vertex_sets}
    hyperedges = []
    for table in edge_tables:
        roles = tuple(column.removesuffix("_id") for column, _ in table.foreign_keys)
        connects = tuple(by_instance.get(target, _placeholder_type(target)) for _, target in table.foreign_keys)
        symmetric: tuple[str, ...] = ()
        if table.check:
            symmetric = tuple(name.removesuffix("_id") for name in table.check)
        _report_positional_ambiguity(table, roles, losses)
        hyperedges.append(
            Hyperedge(
                name=table.name,
                connects=connects,
                roles=roles,
                symmetric=symmetric,
                fields=tuple(table.fields),
            )
        )

    model = Model(
        name=system_name,
        vertex_sets=tuple(vertex_sets),
        hyperedges=tuple(hyperedges),
        constraints=(),
    )
    if not read_comments:
        losses.append(
            Loss("unrecoverable", "system name: carried in a comment, not in executable SQL")
        )
    # Constraints are lost in both tiers. `translate` evaluates them and emits no
    # constraints block, so no reader can recover them, and a report that stayed
    # silent here would claim a completeness the round trip does not have.
    losses.append(
        Loss(
            "unrecoverable",
            "declared constraints: `translate` evaluates them and emits none into SQL, "
            "so a recovered model declares nothing",
        )
    )
    return ImportResult(model=model, losses=tuple(losses))


def _read_table(name: str, body: str, losses: list[Loss]) -> _Table:
    table = _Table(name=name)
    for raw in _split_columns(body):
        column = _INLINE_COMMENT.sub("", raw).strip().rstrip(",").strip()
        if not column or column.startswith("id UUID PRIMARY KEY"):
            continue
        label = _LABEL.match(column)
        if label:
            table.has_label = True
            table.label_sql = label.group(1) if "NOT NULL UNIQUE" in column else None
            continue
        foreign_key = _FK.match(column)
        if foreign_key:
            table.foreign_keys.append((foreign_key.group(1), foreign_key.group(2)))
            continue
        unique = _UNIQUE.match(column)
        if unique:
            table.unique = tuple(part.strip() for part in unique.group(1).split(","))
            continue
        check = _CHECK.match(column)
        if check:
            table.check = (check.group(1), check.group(2))
            continue
        field = _FIELD.match(column)
        if field and field.group(2) in _SQL_TO_DECLARED:
            table.fields.append(
                Field(
                    name=field.group(1),
                    type_name=_SQL_TO_DECLARED[field.group(2)],
                    optional=field.group(3) is None,
                )
            )
            continue
        losses.append(Loss("unrecognised", f"column in {name}: {column}"))
    return table


def _split_columns(body: str) -> list[str]:
    """Split a table body on commas that are not inside parentheses."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for character in body:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if character == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(character)
    if current:
        parts.append("".join(current))
    return parts


def _report_positional_ambiguity(table: _Table, roles: tuple[str, ...], losses: list[Loss]) -> None:
    """A positional endpoint and a role literally named `user_1` emit the same column."""
    for role in roles:
        match = _POSITIONAL.match(role)
        if match:
            losses.append(
                Loss(
                    "ambiguous",
                    f"{table.name}.{role}_id: a positional endpoint and a role named "
                    f"{role!r} generate the same column, so which was declared is not recoverable",
                )
            )


def _placeholder_type(instance: str) -> str:
    return instance[:1].upper() + instance[1:]


def render_hks(model: Model) -> str:
    """Render a recovered model back into `.hks` source.

    Deliberately minimal: enough to read what was recovered and to diff it
    against the original by eye. Constraints are not emitted because SQL does
    not carry them, which the loss report says.
    """
    lines = [f"system {model.name} {{"]
    for vertex in model.vertex_sets:
        head = f"    vertices {vertex.instance}: {vertex.type_name}"
        if vertex.label_type:
            head += f" labeled {vertex.label_type}"
        if not vertex.fields:
            lines.append(head)
            continue
        lines.append(head + " {")
        for declared in vertex.fields:
            optional = "?" if declared.optional else ""
            lines.append(f"        {declared.name}: {declared.type_name}{optional}")
        lines.append("    }")
    if model.hyperedges:
        lines.append("")
    for edge in model.hyperedges:
        if edge.roles:
            participants = " ".join(
                f"{role}:{type_name}"
                for role, type_name in zip(edge.roles, edge.connects, strict=True)
            )
        else:
            participants = " ".join(edge.connects)
        line = f"    hyperedges {edge.name}: connect {participants}"
        if edge.symmetric:
            line += f" symmetric({edge.symmetric[0]}, {edge.symmetric[1]})"
        if not edge.fields:
            lines.append(line)
            continue
        lines.append(line + " {")
        for declared in edge.fields:
            optional = "?" if declared.optional else ""
            lines.append(f"        {declared.name}: {declared.type_name}{optional}")
        lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"
