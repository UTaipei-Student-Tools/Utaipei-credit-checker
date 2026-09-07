"""One-shot, privacy-safe smoke test for the UTaipei student portal.

This script never prints credentials, cookies, HTML, PDF contents, or a
student identifier.  It is intentionally separate from the automated test
suite because running it performs a real authenticated request.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from course_input_adapter import adapt_legacy_result  # noqa: E402
from input_confirmation import ConfirmationState, release_formal_attempts  # noqa: E402
from pdf_parser import parse_transcript_pdf  # noqa: E402
from scraper import PORTAL_HOST, PortalClient, PortalError  # noqa: E402


class CredentialFileError(ValueError):
    """Raised without embedding any secret or source line in the message."""


_CONFIRMATION_STATES = frozenset(item.value for item in ConfirmationState)


def _verification_defaults() -> dict[str, object]:
    """Return the fixed, private-data-free transcript verification schema."""

    return {
        "pdf_parse_ok": False,
        "course_rows_present": False,
        "parser_complete": False,
        "parser_fatal": False,
        "reconciliation_available": False,
        "reconciliation_status": "not_available",
        "total_reconciled": False,
        "confirmation_state": ConfirmationState.UNCONFIRMED.value,
        "formal_rows_released": False,
    }


def _verify_transcript_pdf(pdf_bytes: bytes) -> dict[str, object]:
    """Verify the parser and confirmation boundary without returning course data.

    This intentionally calls the same parser and adapter used by the app.  The
    only returned values are booleans and closed-enum states; student fields,
    course rows, diagnostics, fingerprints, and parser exception text never
    cross this boundary.
    """

    result = _verification_defaults()
    if not pdf_bytes.startswith(b"%PDF-"):
        result["error_code"] = "TRANSCRIPT_PARSE_FAILED"
        return result

    try:
        student_info, courses = parse_transcript_pdf(pdf_bytes)
        if not courses:
            result["error_code"] = "TRANSCRIPT_PARSE_FAILED"
            return result

        diagnostics = student_info.get("parse_diagnostics", {}) if isinstance(student_info, dict) else {}
        if not isinstance(diagnostics, dict):
            diagnostics = {}
        parser_complete = bool(diagnostics.get("complete", True))
        parser_fatal = bool(diagnostics.get("fatal", bool(diagnostics.get("fatal_warnings"))))
        reconciliation = diagnostics.get("reconciliation", {})
        if not isinstance(reconciliation, dict):
            reconciliation = {}
        reconciliation_available = bool(reconciliation.get("available", False))
        reconciliation_status = str(reconciliation.get("status", "not_available") or "not_available")
        if reconciliation_status not in {"reconciled", "mismatch", "conflict", "not_available", "limited", "partial"}:
            reconciliation_status = "UNKNOWN"
        total_reconciled = bool(diagnostics.get("total_reconciled", False))

        adapted = adapt_legacy_result(courses, source_kind="transcript")
        confirmation = adapted.confirmation
        confirmation_valid = bool(getattr(confirmation, "valid", False))
        state = getattr(confirmation, "state", None)
        state_value = getattr(state, "value", state)
        state_value = str(state_value or "")
        if state_value not in _CONFIRMATION_STATES:
            state_value = "UNKNOWN"
        released_rows = release_formal_attempts(confirmation, confirmation.fingerprint)

        result.update(
            {
                "pdf_parse_ok": parser_complete and not parser_fatal,
                # A parser result is only useful to the product when the
                # adapter also has at least one normalized row to confirm.
                "course_rows_present": bool(courses) and bool(adapted.rows),
                "parser_complete": parser_complete,
                "parser_fatal": parser_fatal,
                "reconciliation_available": reconciliation_available,
                "reconciliation_status": reconciliation_status,
                "total_reconciled": total_reconciled,
                "confirmation_state": state_value,
                "formal_rows_released": bool(released_rows),
            }
        )
        if not result["parser_complete"] or result["parser_fatal"]:
            result["error_code"] = "TRANSCRIPT_PARSER_INCOMPLETE"
        elif not result["reconciliation_available"]:
            # Missing cumulative fields are a non-fatal parser state, but
            # cannot support a live smoke PASS.
            result["error_code"] = "TRANSCRIPT_RECONCILIATION_UNAVAILABLE"
        elif not result["total_reconciled"]:
            result["error_code"] = "TRANSCRIPT_RECONCILIATION_FAILED"
        elif not (
            result["course_rows_present"]
            and confirmation_valid
            and state_value == ConfirmationState.PARSED.value
            and not result["formal_rows_released"]
        ):
            result["error_code"] = "TRANSCRIPT_CONFIRMATION_UNSAFE"
        return result
    except Exception:
        # Parsing libraries can expose arbitrary exception messages containing
        # private PDF text.  A stable code is the only allowed failure detail.
        result["error_code"] = "TRANSCRIPT_PARSE_FAILED"
        return result


def _split_setting(line: str) -> tuple[str, str] | None:
    match = re.match(r"^\s*([^:=：]+?)\s*[:=：]\s*(.*?)\s*$", line)
    if not match:
        return None
    return match.group(1).strip().lower(), match.group(2).strip()


def load_portal_credentials(path: Path) -> tuple[str, str]:
    """Read only the portal account/password from a local ignored text file."""

    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise CredentialFileError("credential file is unavailable") from exc

    account = ""
    password = ""
    portal_urls: list[str] = []
    for raw_line in text.splitlines():
        setting = _split_setting(raw_line)
        if setting:
            key, value = setting
            is_hf_setting = any(label in key for label in ("hf", "huggingface", "hugging face", "space", "token"))
            if not is_hf_setting and any(
                label in key for label in ("校務帳號", "學生帳號", "學號", "帳號", "portal account", "portal user", "account", "user")
            ):
                account = value
            elif not is_hf_setting and any(
                label in key for label in ("校務密碼", "學生密碼", "密碼", "portal password", "portal pwd", "password", "pwd")
            ):
                password = value
        portal_urls.extend(re.findall(r"https://[^\s]+", raw_line))

    official_urls = [
        value.rstrip(").,，。")
        for value in portal_urls
        if (urlparse(value.rstrip(").,，。")).hostname or "").lower() == PORTAL_HOST
    ]
    if not official_urls or not account or not password:
        raise CredentialFileError("portal URL/account/password fields are incomplete")
    return account, password


def run_smoke(credentials_file: Path) -> dict[str, object]:
    """Run one authenticated transcript lifecycle and return safe metrics."""

    account, password = load_portal_credentials(credentials_file)
    client = PortalClient(account, password)
    started = time.perf_counter()
    login_ms = fetch_ms = None
    try:
        phase = time.perf_counter()
        client.login()
        login_ms = round((time.perf_counter() - phase) * 1000, 1)

        phase = time.perf_counter()
        pdf_bytes = client.fetch_transcript_pdf()
        fetch_ms = round((time.perf_counter() - phase) * 1000, 1)
        pdf_bytes = bytes(pdf_bytes or b"")
        transcript_ok = pdf_bytes.startswith(b"%PDF-")
        verification = _verify_transcript_pdf(pdf_bytes)
        overall_status = (
            "PASS"
            if transcript_ok
            and verification["pdf_parse_ok"]
            and verification["course_rows_present"]
            and verification["parser_complete"]
            and not verification["parser_fatal"]
            and verification["reconciliation_available"]
            and verification["total_reconciled"]
            and verification["confirmation_state"] == ConfirmationState.PARSED.value
            and not verification["formal_rows_released"]
            and "error_code" not in verification
            else "FAILED"
        )
        result = {
            "ok": transcript_ok,
            "overall_status": overall_status,
            "transcript_ok": transcript_ok,
            "login_ms": login_ms,
            "fetch_ms": fetch_ms,
            "total_ms": round((time.perf_counter() - started) * 1000, 1),
            "pdf_nonempty": bool(pdf_bytes),
        }
        result.update(verification)
        result["ok"] = overall_status == "PASS"
        return result
    except PortalError as exc:
        result = {
            "ok": False,
            "error_code": exc.code.value,
            "overall_status": "FAILED",
            "transcript_ok": False,
            "login_ms": login_ms,
            "fetch_ms": fetch_ms,
            "total_ms": round((time.perf_counter() - started) * 1000, 1),
        }
        result.update(_verification_defaults())
        return result
    except Exception:
        result = {
            "ok": False,
            "error_code": "UNEXPECTED_ERROR",
            "overall_status": "FAILED",
            "transcript_ok": False,
            "login_ms": login_ms,
            "fetch_ms": fetch_ms,
            "total_ms": round((time.perf_counter() - started) * 1000, 1),
        }
        result.update(_verification_defaults())
        return result
    finally:
        client.close()
        password = ""
        account = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Privacy-safe UTaipei portal smoke test")
    parser.add_argument("--credentials-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_smoke(args.credentials_file)
    except CredentialFileError:
        result = {"ok": False, "error_code": "CREDENTIAL_FILE_INVALID"}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
