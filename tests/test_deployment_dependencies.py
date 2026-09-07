"""Protect Community Cloud's requirements.txt installation route."""

from pathlib import Path


def test_community_cloud_uses_requirements_txt():
    root = Path(__file__).resolve().parents[1]
    assert (root / "app.py").is_file()
    requirements = root / "requirements.txt"
    assert requirements.is_file() and requirements.read_text(encoding="utf-8").strip()
    # Community Cloud selects these before requirements.txt. Introducing one
    # requires an intentional migration, not an empty placeholder lockfile.
    for filename in ("uv.lock", "Pipfile", "environment.yml"):
        assert not (root / filename).exists(), f"{filename} shadows requirements.txt"
