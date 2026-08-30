"""The committed diagram is a build artifact, so something has to notice when it goes stale."""


def test_the_committed_diagram_matches_its_source():
    """The .svg in docs/diagrams is a build artifact, so it can go stale silently.

    This regenerates it and compares. It skips when d2 is not installed rather than
    failing, because CI has no d2 and a red build for a missing optional tool trains
    people to ignore red builds. Locally, where diagrams actually get edited, it runs.
    """
    import shutil
    import subprocess
    from pathlib import Path

    import pytest

    if shutil.which("d2") is None:
        pytest.skip("d2 is not installed; run `make diagrams` where it is")

    root = Path(__file__).resolve().parent.parent
    sources = sorted((root / "docs" / "diagrams").glob("*.d2"))
    assert sources, "no .d2 sources found"

    for src in sources:
        committed = src.with_suffix(".svg")
        assert committed.exists(), f"{committed.name} has never been generated"
        fresh = subprocess.run(
            ["d2", "--theme", "0", "--dark-theme", "200", "--pad", "24", str(src), "-"],
            capture_output=True, text=True, check=True,
        ).stdout
        assert fresh == committed.read_text(), (
            f"{committed.name} is not what {src.name} produces; run `make diagrams`"
        )
