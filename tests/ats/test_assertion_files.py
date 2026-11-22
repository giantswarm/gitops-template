"""Checks of which assertion files the kind test loads; they need no cluster."""

from pathlib import Path

from checks import assertion_files


def test_load_assertions_leaves_out_the_skipped_examples(tmp_path: Path) -> None:
    # the files and directories of an example that isn't there are left out, the rest stays
    for path in ("gone/a.yaml", "gone.yaml", "there/b.yaml", "gone-not/c.yaml"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("kind: ConfigMap\nmetadata:\n  name: x\n")
    skipped = {str(tmp_path / "gone"): "gone", str(tmp_path / "gone.yaml"): "gone"}
    assertions = assertion_files.load_assertions(str(tmp_path), skipped)
    assert sorted(assertions) == [
        str(tmp_path / "gone-not/c.yaml"),
        str(tmp_path / "there/b.yaml"),
    ]
