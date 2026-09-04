"""A hand-written lexer and recursive-descent parser for the `.hks` subset.

Grammar accepted (whitespace and newlines are insignificant except inside the
operations block, whose bodies are captured raw):

    program     := system constraints? operations?
    system      := 'system' NAME '{' vertexdecl* hyperdecl* '}'
    vertexdecl  := 'vertices' NAME ':' TYPE ('labeled' TYPE)? fieldblock?
    fieldblock  := '{' (NAME ':' TYPE '?'?)* '}'
    hyperdecl   := 'hyperedges' NAME ':' 'connect' participant participant+ symmetry? fieldblock?
    participant := (ROLE ':')? TYPE
    symmetry    := 'symmetric' '(' ROLE ',' ROLE ')'
    constraints := 'constraints' '{' constraint* '}'
    constraint  := NAME ('(' INT ')')?
    operations  := 'operations' '{' opdef* '}'

`#` and `//` start a line comment.
"""

from __future__ import annotations

import re
from pathlib import Path

from .errors import DuplicateNameError
from .errors import ParseError
from .model import Constraint
from .model import Field
from .model import FIELD_TYPES
from .model import GENERATED_COLUMNS
from .model import Hyperedge
from .model import Model
from .model import Operation
from .model import VertexSet

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>[ \t\r\n]+)
  | (?P<comment>(?:\#|//)[^\n]*)
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<int>[0-9]+)
  | (?P<punct>[{}():,?])
    """,
    re.VERBOSE,
)

_PARAMETERISED_CONSTRAINTS = {"uniform": "k"}
_KNOWN_CONSTRAINTS = {"uniform", "directed", "acyclic", "connected"}


class _Token:
    __slots__ = ("kind", "value", "line", "column")

    def __init__(self, kind: str, value: str, line: int, column: int) -> None:
        self.kind = kind
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"_Token({self.kind}, {self.value!r}, line={self.line})"


def tokenize(source: str) -> list[_Token]:
    """Split source into tokens, raising ParseError on an unrecognised character."""
    tokens: list[_Token] = []
    position = 0
    line = 1
    line_start = 0
    length = len(source)
    while position < length:
        match = _TOKEN_RE.match(source, position)
        if match is None:
            raise ParseError(
                f"unexpected character {source[position]!r}",
                line,
                position - line_start + 1,
            )
        text = match.group(0)
        kind = match.lastgroup
        assert kind is not None
        if kind not in ("ws", "comment"):
            tokens.append(_Token(kind, text, line, position - line_start + 1))
        newlines = text.count("\n")
        if newlines:
            line += newlines
            line_start = position + text.rfind("\n") + 1
        position = match.end()
    tokens.append(_Token("eof", "", line, 0))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._index = 0

    # -- token helpers -------------------------------------------------

    @property
    def current(self) -> _Token:
        return self._tokens[self._index]

    def advance(self) -> _Token:
        token = self._tokens[self._index]
        if token.kind != "eof":
            self._index += 1
        return token

    def at(self, kind: str, value: str | None = None) -> bool:
        token = self.current
        return token.kind == kind and (value is None or token.value == value)

    def expect(self, kind: str, value: str | None = None) -> _Token:
        token = self.current
        if not self.at(kind, value):
            wanted = value if value is not None else kind
            got = token.value if token.kind != "eof" else "end of file"
            raise ParseError(f"expected {wanted!r}, found {got!r}", token.line, token.column)
        return self.advance()

    def expect_name(self) -> _Token:
        token = self.current
        if token.kind != "name":
            got = token.value if token.kind != "eof" else "end of file"
            raise ParseError(f"expected a name, found {got!r}", token.line, token.column)
        return self.advance()

    # -- grammar -------------------------------------------------------

    def parse_program(self) -> Model:
        name, vertex_sets, hyperedges = self.parse_system()
        constraints: tuple[Constraint, ...] = ()
        operations: tuple[Operation, ...] = ()
        while not self.at("eof"):
            if self.at("name", "constraints"):
                if constraints:
                    raise ParseError(
                        "a second `constraints` block", self.current.line, self.current.column
                    )
                constraints = self.parse_constraints()
            elif self.at("name", "operations"):
                if operations:
                    raise ParseError(
                        "a second `operations` block", self.current.line, self.current.column
                    )
                operations = self.parse_operations()
            else:
                token = self.current
                raise ParseError(
                    f"expected `constraints` or `operations`, found {token.value!r}",
                    token.line,
                    token.column,
                )
        return Model(
            name=name,
            vertex_sets=vertex_sets,
            hyperedges=hyperedges,
            constraints=constraints,
            operations=operations,
        )

    def parse_system(self) -> tuple[str, tuple[VertexSet, ...], tuple[Hyperedge, ...]]:
        self.expect("name", "system")
        name = self.expect_name().value
        self.expect("punct", "{")
        vertex_sets: list[VertexSet] = []
        hyperedges: list[Hyperedge] = []
        seen_instances: set[str] = set()
        seen_edges: set[str] = set()
        while not self.at("punct", "}"):
            token = self.current
            if token.kind == "eof":
                raise ParseError("unterminated `system` block", token.line, token.column)
            if self.at("name", "vertices"):
                vertex_set = self.parse_vertex_decl()
                if vertex_set.instance in seen_instances:
                    raise DuplicateNameError("vertex set", vertex_set.instance)
                seen_instances.add(vertex_set.instance)
                vertex_sets.append(vertex_set)
            elif self.at("name", "hyperedges"):
                hyperedge = self.parse_hyperedge_decl()
                if hyperedge.name in seen_edges:
                    raise DuplicateNameError("hyperedge", hyperedge.name)
                seen_edges.add(hyperedge.name)
                hyperedges.append(hyperedge)
            else:
                raise ParseError(
                    f"expected `vertices` or `hyperedges`, found {token.value!r}",
                    token.line,
                    token.column,
                )
        self.expect("punct", "}")
        if not vertex_sets:
            raise ParseError(f"system {name!r} declares no vertices", self.current.line)
        return name, tuple(vertex_sets), tuple(hyperedges)

    def parse_vertex_decl(self) -> VertexSet:
        keyword = self.expect("name", "vertices")
        instance = self.expect_name().value
        self.expect("punct", ":")
        type_name = self.expect_name().value
        label_type: str | None = None
        if self.at("name", "labeled"):
            self.advance()
            label_token = self.expect_name()
            label_type = label_token.value
            if label_type not in FIELD_TYPES:
                raise ParseError(
                    f"vertex set {instance!r} is labeled {label_type!r}, which is not one of "
                    f"{', '.join(FIELD_TYPES)}",
                    label_token.line,
                    label_token.column,
                )
        fields = (
            self.parse_field_block(f"vertex set {instance!r}")
            if self.at("punct", "{")
            else ()
        )
        return VertexSet(
            instance=instance,
            type_name=type_name,
            label_type=label_type,
            fields=fields,
            line=keyword.line,
        )

    def parse_field_block(
        self, owner: str, reserved: tuple[str, ...] = GENERATED_COLUMNS
    ) -> tuple[Field, ...]:
        """`{ name: Type[?] ... }` on a vertex declaration.

        An unrecognised type is refused rather than defaulted. Choosing a column
        type the model never declared is the legacy behaviour this package
        exists to avoid.
        """
        opening = self.expect("punct", "{")
        fields: list[Field] = []
        seen: set[str] = set()
        while not self.at("punct", "}"):
            token = self.expect_name()
            name = token.value
            self.expect("punct", ":")
            type_name = self.expect_name().value
            optional = False
            if self.at("punct", "?"):
                self.advance()
                optional = True
            if name in reserved:
                raise ParseError(
                    f"{owner} declares a field {name!r}, which every "
                    "generated schema already defines",
                    token.line,
                    token.column,
                )
            if name in seen:
                raise ParseError(
                    f"{owner} declares the field {name!r} twice",
                    token.line,
                    token.column,
                )
            if type_name not in FIELD_TYPES:
                raise ParseError(
                    f"field {name!r} names the type {type_name!r}, which is not one of "
                    f"{', '.join(FIELD_TYPES)}",
                    token.line,
                    token.column,
                )
            seen.add(name)
            fields.append(Field(name=name, type_name=type_name, optional=optional, line=token.line))
        self.expect("punct", "}")
        if not fields:
            raise ParseError(
                f"{owner} declares an empty field block; omit it instead",
                opening.line,
                opening.column,
            )
        return tuple(fields)

    def parse_hyperedge_decl(self) -> Hyperedge:
        keyword = self.expect("name", "hyperedges")
        name = self.expect_name().value
        self.expect("punct", ":")
        self.expect("name", "connect")
        connects: list[str] = []
        roles: list[str | None] = []
        while True:
            first = self.expect_name().value
            if self.at("punct", ":"):
                self.advance()
                roles.append(first)
                connects.append(self.expect_name().value)
            else:
                roles.append(None)
                connects.append(first)
            if self.current.kind != "name" or self.current.value in (
                "vertices",
                "hyperedges",
                "symmetric",
            ):
                break
        if len(connects) < 2:
            raise ParseError(
                f"hyperedge {name!r} must connect at least two vertex types",
                keyword.line,
                keyword.column,
            )
        named = [role for role in roles if role is not None]
        if named and len(named) != len(roles):
            raise ParseError(
                f"hyperedge {name!r} gives a role to some participants and not others; "
                "roles are all or nothing",
                keyword.line,
                keyword.column,
            )
        seen: set[str] = set()
        for role in named:
            if role in seen:
                raise ParseError(
                    f"hyperedge {name!r} uses the role {role!r} twice; "
                    "each participant needs its own role",
                    keyword.line,
                    keyword.column,
                )
            seen.add(role)
        symmetric: tuple[str, ...] = ()
        if self.at("name", "symmetric"):
            self.advance()
            self.expect("punct", "(")
            pair = [self.expect_name().value]
            self.expect("punct", ",")
            pair.append(self.expect_name().value)
            self.expect("punct", ")")
            if not named:
                raise ParseError(
                    f"hyperedge {name!r} declares symmetric() but its participants have no "
                    "role names; symmetry names roles, not positions",
                    keyword.line,
                    keyword.column,
                )
            if pair[0] == pair[1]:
                raise ParseError(
                    f"hyperedge {name!r} declares the role {pair[0]!r} symmetric with itself; "
                    "symmetry names two distinct roles",
                    keyword.line,
                    keyword.column,
                )
            for role in pair:
                if role not in named:
                    raise ParseError(
                        f"hyperedge {name!r} declares {role!r} symmetric, but no participant "
                        f"has that role",
                        keyword.line,
                        keyword.column,
                    )
            symmetric = tuple(pair)
        edge_fields = (
            self.parse_field_block(f"hyperedge {name!r}", reserved=("id",))
            if self.at("punct", "{")
            else ()
        )
        return Hyperedge(
            name=name,
            connects=tuple(connects),
            roles=tuple(named),
            symmetric=symmetric,
            fields=edge_fields,
            line=keyword.line,
        )

    def parse_constraints(self) -> tuple[Constraint, ...]:
        self.expect("name", "constraints")
        self.expect("punct", "{")
        constraints: list[Constraint] = []
        while not self.at("punct", "}"):
            token = self.current
            if token.kind == "eof":
                raise ParseError("unterminated `constraints` block", token.line, token.column)
            kind = self.expect_name().value
            if kind not in _KNOWN_CONSTRAINTS:
                supported = ", ".join(sorted(_KNOWN_CONSTRAINTS))
                raise ParseError(
                    f"unknown constraint {kind!r}; supported: {supported}",
                    token.line,
                    token.column,
                )
            parameters: tuple[tuple[str, int], ...] = ()
            if self.at("punct", "("):
                self.advance()
                value_token = self.current
                if value_token.kind != "int":
                    raise ParseError(
                        f"constraint {kind!r} expects an integer parameter",
                        value_token.line,
                        value_token.column,
                    )
                self.advance()
                self.expect("punct", ")")
                parameter_name = _PARAMETERISED_CONSTRAINTS.get(kind)
                if parameter_name is None:
                    raise ParseError(
                        f"constraint {kind!r} takes no parameter", token.line, token.column
                    )
                parameters = ((parameter_name, int(value_token.value)),)
            elif kind in _PARAMETERISED_CONSTRAINTS:
                raise ParseError(
                    f"constraint {kind!r} requires a parameter, e.g. {kind}(2)",
                    token.line,
                    token.column,
                )
            if self.at("punct", ","):
                self.advance()
            constraints.append(Constraint(kind=kind, parameters=parameters, line=token.line))
        self.expect("punct", "}")
        return tuple(constraints)

    def parse_operations(self) -> tuple[Operation, ...]:
        """Parse `operations { ... }` structurally, then keep the bodies as text.

        This block is deliberately not interpreted. See the plan's non-goals: it
        is parsed only so a legacy-shaped file loads, and the CLI reports how
        many operations it ignored.
        """
        self.expect("name", "operations")
        self.expect("punct", "{")
        operations: list[Operation] = []
        while not self.at("punct", "}"):
            token = self.current
            if token.kind == "eof":
                raise ParseError("unterminated `operations` block", token.line, token.column)
            name = self.expect_name().value
            self.expect("punct", "(")
            depth = 1
            while depth:
                inner = self.advance()
                if inner.kind == "eof":
                    raise ParseError(
                        f"unterminated parameter list for operation {name!r}", token.line
                    )
                if inner.kind == "punct" and inner.value == "(":
                    depth += 1
                elif inner.kind == "punct" and inner.value == ")":
                    depth -= 1
            self.expect("punct", ":")
            self.expect_name()
            self.expect("punct", "{")
            body_parts: list[str] = []
            depth = 1
            while depth:
                inner = self.advance()
                if inner.kind == "eof":
                    raise ParseError(f"unterminated body for operation {name!r}", token.line)
                if inner.kind == "punct" and inner.value == "{":
                    depth += 1
                elif inner.kind == "punct" and inner.value == "}":
                    depth -= 1
                    if depth == 0:
                        break
                body_parts.append(inner.value)
            operations.append(
                Operation(name=name, raw_body=" ".join(body_parts), line=token.line)
            )
        self.expect("punct", "}")
        return tuple(operations)


def parse_source(source: str) -> Model:
    """Parse `.hks` source text into a declared Model."""
    return _Parser(tokenize(source)).parse_program()


def parse_file(path: str | Path) -> Model:
    """Parse an `.hks` file from disk."""
    return parse_source(Path(path).read_text(encoding="utf-8"))
