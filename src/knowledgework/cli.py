"""The `knowledgework` command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .backends import BACKENDS
from .constraints import evaluate_constraints
from .constraints import render_verdict_report
from .errors import KnowledgeworkError
from .parser import parse_file
from .resolve import resolve_model


def _translate(source: Path, out_dir: Path, stream) -> int:
    model = parse_file(source)
    resolved = resolve_model(model)

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, generator in BACKENDS.values():
        target = out_dir / f"{source.stem}.{filename}"
        target.write_text(generator(resolved), encoding="utf-8")  # type: ignore[operator]
        written.append(target)

    print(f"Read {source}", file=stream)
    print(
        f"  system {model.name}: {len(model.vertex_sets)} vertex set(s), "
        f"{len(model.hyperedges)} hyperedge(s), {len(model.constraints)} declared constraint(s)",
        file=stream,
    )
    if model.operations:
        names = ", ".join(op.name for op in model.operations)
        print(
            f"  parsed and IGNORED {len(model.operations)} operation(s): {names}. "
            f"Operation bodies are not analysed in this slice and affect no verdict.",
            file=stream,
        )
    print("", file=stream)
    print("Wrote:", file=stream)
    for target in written:
        print(f"  {target}", file=stream)
    print("", file=stream)
    print(render_verdict_report(resolved, evaluate_constraints(resolved)), file=stream)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowledgework",
        description="Translate one declared model into backend schemas and report on its constraints.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    translate = subparsers.add_parser(
        "translate", help="Generate backend schemas and print the constraint verdict."
    )
    translate.add_argument("source", type=Path, help="Path to a .hks model file.")
    translate.add_argument(
        "--out",
        type=Path,
        default=Path("generated"),
        help="Directory for generated schemas (default: generated/, which is git-ignored).",
    )
    read_back = subparsers.add_parser(
        "import",
        help="recover a model from PostgreSQL this package generated",
    )
    read_back.add_argument("schema", help="a .sql file produced by `translate`")
    read_back.add_argument(
        "--read-comments",
        action="store_true",
        help="admit generated comments, which carry the type names executable SQL does not",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "translate":
        try:
            return _translate(args.source, args.out, sys.stdout)
        except KnowledgeworkError as error:
            print(f"knowledgework: {type(error).__name__}: {error}", file=sys.stderr)
            return 1
        except FileNotFoundError as error:
            print(f"knowledgework: no such file: {error.filename}", file=sys.stderr)
            return 1
    if args.command == "import":
        return _import(args.schema, args.read_comments, sys.stdout)
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover


def _import(schema: str, read_comments: bool, out) -> int:
    from .importers import import_postgres
    from .importers import render_hks

    result = import_postgres(Path(schema).read_text(encoding="utf-8"), read_comments=read_comments)
    print(render_hks(result.model), file=out)
    if not result.losses:
        print("Nothing reported unrecovered.", file=out)
        return 0
    print(f"{len(result.losses)} thing(s) did not survive the trip:", file=out)
    for loss in result.losses:
        print(f"  {loss.kind:<14} {loss.detail}", file=out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
