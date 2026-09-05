"""Sanitized AG102 transcript diagnostics for the authorized portal account.

Only a closed schema is emitted. Values, arbitrary paths or headers, query
strings, cookies, HTML/PDF bodies, account identifiers, and exception details
are excluded.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bs4 import BeautifulSoup  # noqa: E402

from scraper import (  # noqa: E402
    BASE_URL,
    FNC_URL,
    PortalClient,
    PortalError,
    _find_form,
    _form_controls,
    _has_fnc_identity,
    _has_session_identity,
    _header_value,
    _is_binary_pdf_response,
    _is_captcha_page,
    _is_login_page,
    _response_url,
    _safe_portal_url,
    is_maintenance_page,
)
from scripts.portal_live_smoke import CredentialFileError, load_portal_credentials  # noqa: E402

_KNOWN_CONTROL_NAMES = frozenset(
    {
        "check_choice",
        "chk",
        "chk3",
        "flag",
        "fncid",
        "hid_atd",
        "hid_choice_check",
        "hid_dorm_room",
        "hid_std_choice",
        "hid_std_vote",
        "hid_teach_roll",
        "hid_type",
        "myway",
        "pass",
        "pwd",
        "rst",
        "std_choice",
        "std_dorm",
        "std_vote",
        "teach_roll",
        "uid",
    }
)
_ROUTE_SUFFIXES = (
    ("/utaipei/index_main.html", "ENTRY"),
    ("/utaipei/login_check.jsp", "LOGIN_CHECK"),
    ("/utaipei/perchk.jsp", "PERCHK"),
    ("/utaipei/fnc.jsp", "FNC"),
    ("/utaipei/ag_pro/ag102.jsp", "AG102"),
)


def _route_code(value: object, base_url: str = BASE_URL) -> str:
    """Map a URL to a closed enum without echoing server-controlled paths."""

    parsed = urlparse(urljoin(base_url, str(value or "")))
    if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() != "my.utaipei.edu.tw":
        return "EXTERNAL_OR_INVALID"
    path = (parsed.path or "/").lower().rstrip("/") or "/"
    for suffix, code in _ROUTE_SUFFIXES:
        if path.endswith(suffix):
            return code
    return "OTHER_OFFICIAL"


def _mime_code(value: object) -> str:
    mime = str(value or "").split(";", 1)[0].strip().lower()
    if "html" in mime:
        return "HTML"
    if "pdf" in mime:
        return "PDF"
    if mime in {"application/octet-stream", "binary/octet-stream"}:
        return "OCTET_STREAM"
    return "OTHER"


def _encoding_code(value: object) -> str:
    encoding = str(value or "").strip().lower().replace("_", "-")
    if encoding in {"utf-8", "utf8", "utf-8-sig"}:
        return "UTF8"
    if encoding in {"big5", "big-5", "cp950"}:
        return "BIG5"
    return "OTHER"


def _known_control_names(nodes: object) -> list[str]:
    return sorted(
        {
            name
            for node in nodes
            if (name := str(node.get("name") or "").strip().lower()) in _KNOWN_CONTROL_NAMES
        }
    )


def _control_role(node) -> str:
    text = " ".join(
        str(node.get(attribute) or "")
        for attribute in ("type", "value", "title", "aria-label", "onclick")
    ).lower()
    if any(marker in text for marker in ("回上一頁", "返回", "回主選單", "goback", "fnc.jsp")):
        return "BACK"
    if any(marker in text for marker in ("查詢", "確定", "送出", "執行", "query", "search", "submit")):
        return "QUERY"
    if any(marker in text for marker in ("列印", "print")):
        return "PRINT"
    return "OTHER"


def _describe(response: object) -> dict[str, object]:
    """Project one response into a bounded, transcript-safe report."""

    content_type = _header_value(response, "Content-Type")
    mime_code = _mime_code(content_type)
    result: dict[str, object] = {
        "status": int(getattr(response, "status_code", 0) or 0),
        "route": _route_code(getattr(response, "url", "")),
        "mime": mime_code,
        "content_length_present": bool(_header_value(response, "Content-Length")),
        "content_disposition_present": bool(_header_value(response, "Content-Disposition")),
        "binary_pdf_metadata": _is_binary_pdf_response(response),
        "response_encoding": _encoding_code(getattr(response, "encoding", None)),
        "apparent_encoding": _encoding_code(getattr(response, "apparent_encoding", None)),
    }
    if mime_code != "HTML":
        return result
    html = getattr(response, "text", "") or ""
    soup = BeautifulSoup(html, "html.parser")
    forms = []
    for form in soup.find_all("form"):
        nodes = form.find_all(["input", "select", "button"])
        known_controls = _known_control_names(nodes)
        named_count = sum(bool(node.get("name")) for node in nodes)
        form_id = str(form.get("id") or "").strip().lower()
        form_id_code = form_id.upper() if form_id in {"login", "thisform", "thisform1"} else "OTHER"
        method = str(form.get("method") or "GET").upper()
        if method not in {"GET", "POST"}:
            method = "OTHER"
        forms.append(
            {
                "id": form_id_code,
                "action_route": _route_code(form.get("action"), getattr(response, "url", BASE_URL)),
                "method": method,
                "known_control_names": known_controls,
                "unknown_named_control_count": max(0, named_count - len(known_controls)),
                "select_count": len(form.find_all("select")),
            }
        )
    tables = soup.find_all("table")
    normalized_text = " ".join(soup.get_text(" ", strip=True).split()).lower()
    control_roles = {role: 0 for role in ("BACK", "OTHER", "PRINT", "QUERY")}
    for control in soup.find_all(["input", "button"]):
        control_roles[_control_role(control)] += 1
    result.update(
        {
            "form_count": len(forms),
            "forms": forms,
            "login_page": _is_login_page(html),
            "captcha_page": _is_captcha_page(html),
            "maintenance_page": is_maintenance_page(html),
            "session_identity": _has_session_identity(html),
            "ag102_identity": _has_fnc_identity(html, "AG102"),
            "table_count": len(tables),
            "table_shapes": [
                {
                    "rows": len(table.find_all("tr")),
                    "cells": len(table.find_all(["th", "td"])),
                    "links": len(table.find_all("a")),
                    "inputs": len(table.find_all(["input", "select", "button"])),
                }
                for table in tables[:5]
            ],
            "semantic_flags": {
                "transcript": any(marker in normalized_text for marker in ("成績單", "歷年成績", "學業成績")),
                "no_data": any(marker in normalized_text for marker in ("查無", "無資料", "沒有資料", "無符合")),
                "invalid_parameter": any(marker in normalized_text for marker in ("請輸入", "請選擇", "參數")),
                "not_open": any(marker in normalized_text for marker in ("尚未開放", "未開放")),
                "error": any(marker in normalized_text for marker in ("錯誤", "失敗", "error", "exception")),
                "student_id_label": any(marker in normalized_text for marker in ("學號", "學生代碼")),
            },
            "script_alert_present": any("alert(" in (node.string or "").lower() for node in soup.find_all("script")),
            "frame_count": len(soup.find_all(["frame", "iframe"])),
            "interactive_counts": {
                "anchors": len(soup.find_all("a")),
                "buttons": len(soup.find_all("button")),
                "inputs": len(soup.find_all("input")),
                "onclick": len(soup.find_all(attrs={"onclick": True})),
            },
            "control_roles": control_roles,
        }
    )
    script_text = "\n".join(node.string or "" for node in soup.find_all("script"))
    body = soup.find("body")
    result["script_shape"] = {
        "body_onload_present": bool(body and body.get("onload")),
        "external_script_count": len(soup.find_all("script", src=True)),
        "function_definition_count": len(
            re.findall(r"\bfunction\s+[A-Za-z_$][\w$]*\s*\(", script_text, flags=re.IGNORECASE)
        ),
        "inline_script_count": len([node for node in soup.find_all("script") if not node.get("src")]),
    }
    script_routes = {
        _route_code(match.group(0), getattr(response, "url", BASE_URL))
        for match in re.finditer(r"[A-Za-z0-9_./?-]+\.jsp(?:\?[^\s\"']*)?", script_text, flags=re.IGNORECASE)
    }
    result["known_script_routes"] = sorted(code for code in script_routes if code != "OTHER_OFFICIAL")
    result["other_script_route_present"] = "OTHER_OFFICIAL" in script_routes
    result["script_behavior"] = {
        "async_request_present": bool(
            re.search(r"\b(?:fetch\s*\(|xmlhttprequest\b|[.$]\s*ajax\s*\()", script_text, flags=re.IGNORECASE)
        ),
        "document_write_present": bool(
            re.search(r"\bdocument\s*\.\s*write(?:ln)?\s*\(", script_text, flags=re.IGNORECASE)
        ),
        "form_submit_present": bool(re.search(r"\.\s*submit\s*\(", script_text, flags=re.IGNORECASE)),
        "location_navigation_present": bool(
            re.search(
                r"(?:\b(?:window|top|parent|self|opener)\s*\.\s*)?location(?:\s*\.\s*href)?\s*="
                r"|\blocation\s*\.\s*(?:assign|replace)\s*\(",
                script_text,
                flags=re.IGNORECASE,
            )
        ),
        "opener_access_present": bool(re.search(r"\b(?:window\s*\.\s*)?opener\b", script_text, flags=re.IGNORECASE)),
        "popup_open_present": bool(re.search(r"\bwindow\s*\.\s*open\s*\(", script_text, flags=re.IGNORECASE)),
        "post_message_present": bool(re.search(r"\bpostmessage\s*\(", script_text, flags=re.IGNORECASE)),
        "window_close_present": bool(re.search(r"\b(?:window\s*\.\s*)?close\s*\(", script_text, flags=re.IGNORECASE)),
    }
    return result


def diagnose(credentials_file: Path) -> dict[str, object]:
    """Run the audited login → AG102 form → PDF lifecycle."""

    account, password = load_portal_credentials(credentials_file)
    client = PortalClient(account, password)
    report: dict[str, object] = {"ok": False, "stages": []}
    try:
        client.login()
        report["stages"].append({"stage": "login", "ok": True, "route": _route_code(client._last_response_url)})
        fnc_response = client._create_fnc("AG102")
        report["stages"].append({"stage": "ag102_fnc", "ok": True, **_describe(fnc_response)})
        form = _find_form(fnc_response)
        if form is None:
            report["error_code"] = "AG102_FORM_MISSING"
            return report
        action = _safe_portal_url(
            form.get("action") or BASE_URL + "ag_pro/ag102.jsp",
            _response_url(fnc_response, FNC_URL),
        )
        payload = _form_controls(form)
        report["stages"].append(
            {
                "stage": "ag102_form_contract",
                "ok": True,
                "action_route": _route_code(action),
                "known_control_names": sorted(
                    str(name).lower() for name in payload if str(name).lower() in _KNOWN_CONTROL_NAMES
                ),
                "unknown_control_count": sum(str(name).lower() not in _KNOWN_CONTROL_NAMES for name in payload),
            }
        )
        result = client._request(
            "POST",
            action,
            referer=_response_url(fnc_response, FNC_URL),
            data=payload,
            stream=True,
        )
        report["stages"].append({"stage": "ag102_submit", "ok": True, **_describe(result)})
        # Keep diagnostics on the exact product extraction path.  AG102 can
        # legitimately return an HTML wrapper containing an iframe/embed/link;
        # PortalClient._extract_pdf follows those candidates and applies the
        # same origin, login, size, and PDF-signature guards as production.
        try:
            pdf = client._extract_pdf(result)
        except PortalError as exc:
            report["stages"].append({"stage": "ag102_pdf", "ok": False, "error_code": exc.code.value})
            report["error_code"] = exc.code.value
            return report
        report["stages"].append(
            {"stage": "ag102_pdf", "ok": pdf.startswith(b"%PDF-"), "pdf_nonempty": bool(pdf)}
        )
        report["ok"] = pdf.startswith(b"%PDF-")
        return report
    except PortalError as exc:
        report["error_code"] = exc.code.value
        return report
    except Exception:
        report["error_code"] = "UNEXPECTED_ERROR"
        return report
    finally:
        client.close()
        account = ""
        password = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitized UTaipei AG102 transcript diagnostic")
    parser.add_argument("--credentials-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = diagnose(args.credentials_file)
    except CredentialFileError:
        result = {"ok": False, "error_code": "CREDENTIAL_FILE_INVALID", "stages": []}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
