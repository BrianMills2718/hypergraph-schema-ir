"""End-to-end CLI tests against the documented command."""

from __future__ import annotations

from knowledgework.cli import main


def test_translate_writes_three_files_and_verdict(examples_dir, tmp_path, capsys) -> None:
    exit_code = main(
        ["translate", str(examples_dir / "social-network.hks"), "--out", str(tmp_path)]
    )
    assert exit_code == 0

    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == [
        "social-network.schema.graphql",
        "social-network.schema.mongodb.js",
        "social-network.schema.sql",
    ]

    out = capsys.readouterr().out
    # All four verdict states appear in one run.
    assert "HOLDS" in out
    assert "VIOLATED" in out
    assert "UNEVALUATED" in out
    assert "NOT APPLICABLE" in out
    # The ignored operations block is reported at the point of use.
    assert "parsed and IGNORED 1 operation(s): getFriends" in out


def test_unknown_type_exits_nonzero_with_named_error(tmp_path, capsys) -> None:
    source = tmp_path / "broken.hks"
    source.write_text(
        "system Broken {\n"
        "    vertices users: User\n"
        "    hyperedges memberships: connect User Community\n"
        "}\n",
        encoding="utf-8",
    )
    exit_code = main(["translate", str(source), "--out", str(tmp_path / "out")])
    assert exit_code == 1

    err = capsys.readouterr().err
    assert "UnknownVertexTypeError" in err
    assert "Community" in err
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())


def test_missing_file_exits_nonzero(tmp_path, capsys) -> None:
    exit_code = main(["translate", str(tmp_path / "nope.hks"), "--out", str(tmp_path)])
    assert exit_code == 1
    assert "no such file" in capsys.readouterr().err
