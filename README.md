# knowledgework

Declare a data model once as a typed n-ary hypergraph. Get PostgreSQL DDL, a
MongoDB collection script and a GraphQL schema, plus a verdict on the model's
declared constraints that distinguishes *held* from *could not be checked*.

Standard library only. No runtime dependencies, no database connection, no
network access. Generated schemas are text; the tool never executes them.

```bash
git clone https://github.com/BrianMills2718/hypergraph-schema-ir
cd hypergraph-schema-ir
pip install -e .
knowledgework translate examples/social-network.hks --out generated/
```

**Part of a wider research cluster.** This repo and
[`factgraph`](https://github.com/BrianMills2718/factgraph) are the same
lineage — factgraph is the Project Graph's declared design successor, which
kept the audit question (which modelling rules survive a transform) and cut
most of the rest after finding it already exists in ORM/LinkML/Object-Role-
Modeling tooling. Both sit inside a wider cluster on canonical semantic
representation and capability reuse for AI-generated software. For current
state, open cross-repo decisions, and how these repos relate, see the
baseline synthesis page in
[`BrianMills2718/vision`](https://github.com/BrianMills2718/vision):
[`wiki/synthesis/ontology-semantic-cluster-baseline-2026-09-07.md`](https://github.com/BrianMills2718/vision/blob/main/wiki/synthesis/ontology-semantic-cluster-baseline-2026-09-07.md).

## The point

A binary graph cannot state a three-way fact as one edge, so it invents a node
to hold it. A relational schema *can* state one — a table with three foreign
keys — but it does not record why those three columns are there. They might be
the participants of one ternary relation. They might be three independent
references that happen to share a row. That distinction is a modelling
decision, and no target schema has a place to keep it.

This keeps it. `connect User User Group` is a declaration of arity, not a shape
a later tool has to infer.

```
system SocialNetwork {
    vertices users: User labeled String
    vertices groups: Group labeled String

    hyperedges memberships: connect User Group
    hyperedges group_interactions: connect User User Group
}

constraints {
    uniform(2)
    directed
    connected
}
```

The fourth line is the one that matters. `group_interactions` connects three
vertex sets at once, and it compiles to a three-column junction table with a
unique constraint across all three, a MongoDB validator, and matching GraphQL
fields — without a hand-written join table anywhere.

## The constraint verdict has four states, not two

Pass/fail merges two different situations: a constraint that was checked and
held, and one nothing could check. The example model declares `directed`, and
a boolean checker has two available answers and both are wrong. Reporting
failure says the model breaks a rule it does not break; reporting success says
direction was verified when nothing examined it.

| state | meaning |
|---|---|
| **holds** | checked, and true |
| **violated** | checked, and false — reported with the specific offender |
| **unevaluated** | declared, but no structural predicate decides it |
| **not applicable** | supported, but this model did not declare it |

`directed` being unevaluated is honest reporting of a gap in the *language*,
not only in the checker: the source syntax cannot express direction, so the
junction tables it generates lose it too.

## Round-tripping

`import` reads a generated schema back into a model.

```bash
knowledgework translate examples/social-network.hks --out generated/
knowledgework import generated/social-network.schema.sql                  # executable SQL only
knowledgework import generated/social-network.schema.sql --read-comments  # admit the comments too
```

Reading only executable SQL it recovers the vertex sets, their fields and
nullability, the hyperedge names, the endpoints in order, the participant roles
and the symmetric pairs. Roles survive as column names; symmetry survives as a
`CHECK` constraint.

Two things do not survive: the declared type names, which appear only in
comments, and the constraint verdict, which is computed at generation time and
never emitted. The reader reports both as lost rather than inventing them.
Re-emitting from the recovered model reproduces the file byte for byte.

The same reader exists for MongoDB, and the two agree — rendering both
recovered models back to source produces identical text.

**This is bounded, and the bound matters:** each reader reads only what this
tool wrote. Reading arbitrary PostgreSQL or MongoDB is a different and harder
problem. What the round trip measures is what the representation carries, not
interoperability with schemas in the wild.

## What it is not

- Not a migration tool. No instance data is loaded, validated or moved.
- Not an ORM. Operation bodies are parsed and ignored.
- No GraphQL reader yet. Translation runs both ways for two of the three targets.
- Field-level constraints (`salary > 0`) are outside the language.
- A prototype that makes one argument carefully, not something to point at a
  production schema.

## Prior art

Declaring an n-ary relation and deriving a junction table is Chen's
entity-relationship model, which has had n-ary relationship sets as a
first-class construct since 1976, and the mapping is textbook. That part is not
new and this repository does not claim it is. What is less common is the
four-state verdict and the round-trip measurement of what each target keeps.

Strictly, the object here is not a hypergraph in the textbook sense — an edge
there is a *set* of vertices and `connect User User Group` repeats one. Edges
here join vertex *sets*, are ordered, and their positions can carry roles,
which makes it a typed, role-bearing n-ary incidence structure.

## Tests

```bash
pip install -e . pytest
pytest
```

88 tests. The parser, resolver, three emitters, two readers, and a negative
control for each constraint state.

## Writeup

[Hypergraphs as an intermediate representation for schema
translation](https://medium.com/@brianmills2718/hypergraphs-as-an-intermediate-representation-for-schema-translation-2bfec08670e8) — the longer argument, with figures.

## License

MIT
