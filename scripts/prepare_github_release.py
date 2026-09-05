"""Prepare a reviewed release in the fixed, isolated GitHub checkout.

This helper only copies an explicit, reviewed payload into ``tmp/github-release``.
It does not create a commit or contact GitHub.  The separate publisher performs
the final parent, index, hash, and fast-forward checks when explicitly asked to
publish.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_hf_bundle import build_manifest  # noqa: E402
from scripts.portal_live_smoke import load_portal_credentials  # noqa: E402

REMOTE = "https://github.com/UTaipei-Student-Tools/Utaipei-credit-checker.git"
CHECKOUT = ROOT / "tmp" / "github-release"
PATHSPEC = ROOT / "tmp" / "github-release-pathspec"
EXPECTED = ROOT / "tmp" / "github-release-expected.json"
EXPECTED_SCHEMA = "utaipei-github-release.v1"
_REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)

# Every Python file copied outside the deterministic HF bundle is named here.
# A new test or maintenance script must be reviewed and added explicitly; a
# broad glob would make local work or an injected file publishable by accident.
GITHUB_EXTRA_FILES: tuple[str, ...] = (
    "scripts/build_hf_bundle.py",
    "scripts/hf_live_browser_smoke.py",
    "scripts/performance_smoke.py",
    "scripts/portal_live_diagnostic.py",
    "scripts/portal_live_smoke.py",
    "scripts/prepare_github_release.py",
    "scripts/publish_github_release.py",
    "tests/browser_acceptance.py",
    "tests/conftest.py",
    "tests/formal_transcript_fixture.py",
    "tests/streamlit_spawn_smoke_app.py",
    "tests/synthetic_transcript_fixture.py",
    "tests/test_allocation_engine.py",
    "tests/test_app_snapshot_integration.py",
    "tests/test_application_resolution.py",
    "tests/test_core.py",
    "tests/test_cs_primary_catalog.py",
    "tests/test_course_input_adapter.py",
    "tests/test_curriculum_registry.py",
    "tests/test_decision_snapshot.py",
    "tests/test_equivalency_audit.py",
    "tests/test_graduation_service.py",
    "tests/test_formal_graduation_integration.py",
    "tests/test_hf_bundle.py",
    "tests/test_hf_live_browser_smoke.py",
    "tests/test_html_performance_batch.py",
    "tests/test_input_confirmation.py",
    "tests/test_lieflat_progress_chart.py",
    "tests/test_minor_program_core.py",
    "tests/test_math_primary_tracks.py",
    "tests/test_math_secondary_constraints.py",
    "tests/test_math_secondary_runtime.py",
    "tests/test_mobile_pwa_shell.py",
    "tests/test_performance_smoke.py",
    "tests/test_policy_audit.py",
    "tests/test_portal_contract.py",
    "tests/test_portal_hard_deadline.py",
    "tests/test_portal_identity.py",
    "tests/test_portal_live_diagnostic.py",
    "tests/test_portal_live_smoke.py",
    "tests/test_primary_handbook_separation.py",
    "tests/test_primary_zero_credit_rules.py",
    "tests/test_public_course_catalog.py",
    "tests/test_pwa_metadata.py",
    "tests/test_report_ui.py",
    "tests/test_rule_coverage_111_115.py",
    "tests/test_scraper_lifecycle.py",
    "tests/test_semantic_corrections.py",
    "tests/test_service_worker.py",
    "tests/test_settings_flow.py",
    "tests/test_snapshot_exports.py",
    "tests/test_snapshot_projection.py",
    "tests/test_snapshot_renderer.py",
    "tests/test_student_export_contract.py",
    "tests/test_synthetic_transcript_fixture.py",
    "tests/test_transcript_only_portal.py",
    "tests/test_transcript_reconciliation.py",
    "tests/test_university_cohort_rules.py",
    "tests/test_release_helpers.py",
)


def git(*args: str) -> str:
    """Run a read-only Git command without returning stderr to callers."""

    result = subprocess.run(
        ["git", "-C", str(CHECKOUT), *args],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8").strip()


def _has_reparse_attribute(info: object) -> bool:
    try:
        attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        attributes = 0
    return bool(attributes & _REPARSE_POINT_ATTRIBUTE)


def _reject_link_or_reparse(path: Path, *, root: Path, missing_code: str) -> Path:
    """Return one regular file beneath root without following links."""

    root = root.resolve(strict=True)
    candidate = Path(os.path.abspath(os.fspath(path)))
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("EXTRA_PATH_INVALID") from error
    current = candidate
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError as error:
            raise ValueError(missing_code) from error
        if current.is_symlink() or _has_reparse_attribute(info):
            raise ValueError("EXTRA_PATH_INVALID")
        if current == root:
            break
        parent = current.parent
        if parent == current:
            raise ValueError("EXTRA_PATH_INVALID")
        current = parent
    if not stat.S_ISREG(candidate.lstat().st_mode):
        raise ValueError("EXTRA_PATH_INVALID")
    return candidate


def _normalise_extra_name(relative: str) -> str:
    name = Path(str(relative)).as_posix()
    if name.startswith("./") or "\\" in name or Path(name).is_absolute():
        raise ValueError("EXTRA_MANIFEST_INVALID")
    if not (name.startswith("scripts/") or name.startswith("tests/")) or not name.casefold().endswith(".py"):
        raise ValueError("EXTRA_MANIFEST_INVALID")
    if any(part in {"", ".", ".."} for part in name.split("/")):
        raise ValueError("EXTRA_MANIFEST_INVALID")
    return name


def _collect_reviewed_extra_payloads(
    root: Path = ROOT,
    *,
    allowed: Sequence[str] = GITHUB_EXTRA_FILES,
) -> dict[str, bytes]:
    """Read only explicitly reviewed Python scripts/tests.

    Existing files outside ``allowed`` are an error, including nested files;
    this makes adding a release-relevant script a visible review decision.
    """

    root = root.resolve(strict=True)
    names = tuple(_normalise_extra_name(item) for item in allowed)
    if len(set(names)) != len(names):
        raise ValueError("EXTRA_MANIFEST_INVALID")
    allowed_set = set(names)
    for folder in ("tests", "scripts"):
        directory = root / folder
        if not os.path.lexists(os.fspath(directory)):
            continue
        directory_info = directory.lstat()
        if directory.is_symlink() or _has_reparse_attribute(directory_info) or not stat.S_ISDIR(directory_info.st_mode):
            raise ValueError("EXTRA_PATH_INVALID")
        for source in sorted(directory.rglob("*.py")):
            relative = source.relative_to(root).as_posix()
            _reject_link_or_reparse(source, root=root, missing_code="EXTRA_PATH_INVALID")
            if relative not in allowed_set:
                raise ValueError("EXTRA_PATH_UNREVIEWED")

    payloads: dict[str, bytes] = {}
    for relative in names:
        source = _reject_link_or_reparse(root / relative, root=root, missing_code="EXTRA_PATH_MISSING")
        payloads[relative] = source.read_bytes()
    return payloads


def _secret_bytes(root: Path = ROOT) -> tuple[bytes, ...]:
    """Load local secret values for exclusion checks without logging them."""

    config_path = root / "HF資訊.txt"
    config = config_path.read_text(encoding="utf-8-sig")
    token = re.search(r"\bhf_[A-Za-z0-9]+\b", config)
    if not token:
        raise ValueError("LOCAL_CONFIG_INVALID")
    values = [token.group().encode("utf-8")]
    values.extend(
        item.encode("utf-8")
        for item in load_portal_credentials(config_path)
        if isinstance(item, str) and len(item) >= 4
    )
    return tuple(values)


def _bundle_payloads(bundle: Path, manifest: Mapping[str, object]) -> tuple[dict[str, bytes], bytes]:
    manifest_bytes = (bundle / "DEPLOYMENT_MANIFEST.json").read_bytes()
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        raise ValueError("SOURCE_CHANGED")
    payloads: dict[str, bytes] = {}
    bundle_root = bundle.resolve(strict=True)
    for relative, info in files.items():
        if not isinstance(relative, str) or not isinstance(info, Mapping):
            raise ValueError("SOURCE_CHANGED")
        path = _reject_link_or_reparse(bundle / relative, root=bundle_root, missing_code="SOURCE_PATH_INVALID")
        payload = path.read_bytes()
        expected_bytes = info.get("bytes")
        expected_hash = info.get("sha256")
        if not isinstance(expected_bytes, int) or not isinstance(expected_hash, str):
            raise ValueError("SOURCE_CHANGED")
        if len(payload) != expected_bytes or hashlib.sha256(payload).hexdigest() != expected_hash:
            raise ValueError("BUNDLE_CHANGED")
        payloads[relative] = payload
    payloads["DEPLOYMENT_MANIFEST.json"] = manifest_bytes
    return payloads, manifest_bytes


def _destination_is_safe(destination: Path, checkout: Path) -> None:
    checkout = checkout.resolve(strict=True)
    candidate = Path(os.path.abspath(os.fspath(destination)))
    try:
        candidate.relative_to(checkout)
    except ValueError as error:
        raise ValueError("DESTINATION_INVALID") from error
    current = candidate
    while True:
        if os.path.lexists(os.fspath(current)):
            info = current.lstat()
            if current.is_symlink() or _has_reparse_attribute(info):
                raise ValueError("DESTINATION_LINK")
        if current == checkout:
            break
        parent = current.parent
        if parent == current:
            raise ValueError("DESTINATION_INVALID")
        current = parent


def _record_files(payloads: Mapping[str, bytes]) -> dict[str, dict[str, object]]:
    return {
        name: {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        for name, payload in sorted(payloads.items())
    }


def prepare_payloads(
    *,
    bundle: Path,
    parent: str,
    root: Path = ROOT,
    checkout: Path = CHECKOUT,
    allowed: Sequence[str] = GITHUB_EXTRA_FILES,
) -> dict[str, object]:
    """Prepare and verify the payload, returning the non-sensitive record."""

    root = root.resolve(strict=True)
    checkout = checkout.resolve(strict=True)
    expected_checkout = root / "tmp" / "github-release"
    if checkout != expected_checkout or checkout.is_symlink():
        raise ValueError("CHECKOUT_INVALID")
    if git("remote", "get-url", "origin") != REMOTE:
        raise ValueError("REMOTE_INVALID")
    if git("rev-parse", "HEAD") != parent or git("status", "--porcelain"):
        raise ValueError("CHECKOUT_CHANGED")

    bundle = bundle.resolve(strict=True)
    manifest_path = bundle / "DEPLOYMENT_MANIFEST.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, Mapping) or manifest != build_manifest(root):
        raise ValueError("SOURCE_CHANGED")

    secrets = _secret_bytes(root)
    payloads, _ = _bundle_payloads(bundle, manifest)
    payloads.update(_collect_reviewed_extra_payloads(root, allowed=allowed))
    payloads[".gitignore"] = (root / ".gitignore").read_bytes() + (
        b"\n# Local agent and editor state\n.agents/\n.codex/\n.pytest_cache/\n.ruff_cache/\n"
    )

    for relative, payload in payloads.items():
        if any(secret and secret in payload for secret in secrets):
            raise ValueError("SECRET_EXCLUSION_FAILED")
        destination = checkout / relative
        _destination_is_safe(destination, checkout)
    for relative, payload in payloads.items():
        destination = checkout / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    if any((checkout / name).read_bytes() != payload for name, payload in payloads.items()):
        raise ValueError("COPY_VERIFICATION_FAILED")

    names = sorted(payloads)
    pathspec_bytes = b"\0".join(name.encode("utf-8") for name in names) + b"\0"
    PATHSPEC.parent.mkdir(parents=True, exist_ok=True)
    PATHSPEC.write_bytes(pathspec_bytes)
    record: dict[str, object] = {
        "schema": EXPECTED_SCHEMA,
        "remote": REMOTE,
        "parent": parent,
        "bundle_digest": manifest["bundle_digest"],
        "pathspec_sha256": hashlib.sha256(pathspec_bytes).hexdigest(),
        "files": _record_files(payloads),
    }
    EXPECTED.write_text(
        json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "prepared": True,
        "runtime_digest": manifest["bundle_digest"],
        "file_count": len(payloads),
        "verified": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--parent", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_payloads(bundle=args.bundle, parent=args.parent), ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        approved = {
            "CHECKOUT_INVALID",
            "REMOTE_INVALID",
            "CHECKOUT_CHANGED",
            "SOURCE_CHANGED",
            "LOCAL_CONFIG_INVALID",
            "SOURCE_PATH_INVALID",
            "BUNDLE_CHANGED",
            "EXTRA_MANIFEST_INVALID",
            "EXTRA_PATH_MISSING",
            "EXTRA_PATH_INVALID",
            "EXTRA_PATH_UNREVIEWED",
            "SECRET_EXCLUSION_FAILED",
            "DESTINATION_INVALID",
            "DESTINATION_LINK",
            "COPY_VERIFICATION_FAILED",
        }
        code = str(error) if isinstance(error, ValueError) and str(error) in approved else type(error).__name__
        print(json.dumps({"prepared": False, "code": code}, ensure_ascii=True))
        raise SystemExit(1) from None
