"""北市大畢業通 Streamlit entrypoint.

The page has one evaluation boundary: parser/crawler rows are confirmed by
the user, ``graduation_service.evaluate`` creates a ``DecisionSnapshot``, and
presentation/export functions consume that same object.  No legacy evaluator
is used here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from html import escape as _escape_html
from typing import Any

import streamlit as st

from course_input_adapter import adapt_legacy_result
from graduation_service import EvaluationRequest, evaluate
from input_confirmation import (
    ConfirmationState,
    CourseConfirmation,
    InputDiagnostic,
    NormalizedCourseRow,
    confirm_confirmation,
    edit_confirmation,
    fingerprint_course_rows,
    mask_person_name,
    mask_student_id,
    release_formal_attempts,
)
from pdf_parser import parse_transcript_pdf
from portal_scope import TRANSCRIPT_SCOPE_KEY
from sidebar import render_setup_panel
from ui_components import collapse_sidebar_if_needed, render_header_card, render_html, setup_page


def _load_presentation_api():
    """Load the snapshot-only renderer/export contract on demand."""

    from snapshot_exports import build_audit_json, build_student_allocation_csv, build_student_pdf
    from snapshot_renderer import render_snapshot

    return render_snapshot, build_student_pdf, build_student_allocation_csv, build_audit_json


def _plain_cache_value(value: object) -> object:
    """Convert the safe request projection into deterministic JSON values.

    ``EvaluationRequest.as_dict()`` is already an allowlisted privacy boundary,
    but it deliberately returns frozen mappings/tuples.  This adapter keeps the
    session cache key deterministic without retaining any source bytes or
    caller-owned objects.
    """

    if isinstance(value, Mapping):
        return {str(key): _plain_cache_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_cache_value(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return f"<bytes:{len(value)}>"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _evaluation_request_cache_key(request: EvaluationRequest) -> str:
    """Return a privacy-safe content key for one evaluation request."""

    payload = json.dumps(
        _plain_cache_value(request.as_dict()),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _new_snapshot_artifact_cache(snapshot: object) -> dict[str, object]:
    snapshot_id = str(getattr(snapshot, "snapshot_id", "") or "")
    if not snapshot_id:
        # Test doubles and legacy callers may not expose the content address.
        # Their object identity is still session-local and cannot be confused
        # with another real DecisionSnapshot.
        snapshot_id = f"object:{id(snapshot)}"
    return {"snapshot_id": snapshot_id, "rendered_html": None, "exports": {}}


def _clear_snapshot_caches() -> None:
    """Drop the current snapshot and its artifacts from this session."""

    st.session_state["_decision_snapshot_cache_key"] = None
    st.session_state["_decision_snapshot_cache_value"] = None
    st.session_state["_snapshot_artifact_cache"] = None
    st.session_state["_exports_ready"] = False
    st.session_state["_analysis_exported"] = False


def _evaluate_cached_snapshot(request: EvaluationRequest) -> object:
    """Evaluate at most once for an identical request in the current session.

    Streamlit reruns the script for every widget event.  The cache intentionally
    lives only in ``st.session_state`` and retains one current snapshot; no
    global/cache-decorator path can mix one student's transcript with another's.
    """

    request_key = _evaluation_request_cache_key(request)
    cached_key = st.session_state.get("_decision_snapshot_cache_key")
    cached_snapshot = st.session_state.get("_decision_snapshot_cache_value")
    if cached_key == request_key and cached_snapshot is not None:
        return cached_snapshot

    # Invalidate before evaluation so an exception while evaluating a changed
    # request cannot leave the previous student's snapshot/artifacts available
    # to a later rerun.
    _clear_snapshot_caches()
    snapshot = evaluate(request)
    st.session_state["_decision_snapshot_cache_key"] = request_key
    st.session_state["_decision_snapshot_cache_value"] = snapshot
    st.session_state["_snapshot_artifact_cache"] = _new_snapshot_artifact_cache(snapshot)
    st.session_state["_exports_ready"] = False
    st.session_state["_analysis_exported"] = False
    return snapshot


def _snapshot_artifact_cache(snapshot: object) -> dict[str, object]:
    """Return the one session-local artifact entry for ``snapshot``."""

    current = st.session_state.get("_snapshot_artifact_cache")
    snapshot_id = _new_snapshot_artifact_cache(snapshot)["snapshot_id"]
    if not isinstance(current, dict) or current.get("snapshot_id") != snapshot_id:
        current = _new_snapshot_artifact_cache(snapshot)
        st.session_state["_snapshot_artifact_cache"] = current
        st.session_state["_exports_ready"] = False
        st.session_state["_analysis_exported"] = False
    return current


def _report_export_state(markup: str, exported: bool) -> str:
    """Synchronize the hidden report marker with the current export state."""

    state = "true" if exported else "false"
    pattern = r"(<(?:span|div)\b[^>]*\bid=[\"']utaipei-analysis-state[\"'][^>]*\bdata-exported=[\"'])(?:true|false)([\"'])"
    return re.sub(pattern, rf"\g<1>{state}\g<2>", markup, count=1)


def _safe_error_message(error: BaseException | object) -> str:
    """Return a fixed user-facing error without exposing exception text."""

    from input_confirmation import classify_user_error

    return classify_user_error(error).message


def _has_ephemeral_value(value: object) -> bool:
    """Return whether a session value contains meaningful transient data."""

    if value is None or value is False:
        return False
    if isinstance(value, (str, bytes, bytearray, memoryview)):
        return bool(value)
    if isinstance(value, (Mapping, list, tuple, set, frozenset)):
        return bool(value)
    return True


def _has_ephemeral_student_state(state: Mapping[str, Any] | None = None) -> bool:
    """Detect every session-only student input that an update could discard.

    This is deliberately a positive allowlist of known transient state rather
    than a check for released/confirmed rows.  In particular, raw uploads,
    parsed-but-unconfirmed rows, manual edits, and a cached unexported snapshot
    all require the same update confirmation.
    """

    state = st.session_state if state is None else state
    if _has_ephemeral_value(state.get("transcript_pdf_bytes")):
        return True
    if _has_ephemeral_value(state.get("transcript_pdf_path")):
        return True

    for key in (
        "_editor_rows",
        "editor_rows",
        "manual_rows",
        "manual_course_rows",
        "manual_courses",
        "manual_input_rows",
        "manual_transcript_rows",
        "pending_manual_rows",
        "course_rows",
        "transcript_rows_editor",
        "confirmed_course_rows",
    ):
        if _has_ephemeral_value(state.get(key)):
            return True

    confirmation = state.get("_parsed_confirmation")
    if confirmation is not None:
        if _has_ephemeral_value(getattr(confirmation, "rows", None)):
            return True
        confirmation_state = getattr(confirmation, "state", None)
        confirmation_value = getattr(confirmation_state, "value", confirmation_state)
        if str(confirmation_value or "").upper() == ConfirmationState.CONFIRMED.value:
            return True
    for key in ("confirmed_input", "input_confirmation", "confirmation"):
        if _has_ephemeral_value(state.get(key)):
            return True
    if _has_ephemeral_value(state.get("transcript_confirmed")):
        return True
    if _has_ephemeral_value(state.get("confirmed_course_fingerprint")):
        return True
    if _has_ephemeral_value(state.get("_source_fingerprint")):
        return True

    if _has_ephemeral_value(state.get(TRANSCRIPT_SCOPE_KEY)):
        return True

    snapshot = state.get("_decision_snapshot_cache_value")
    if snapshot is not None and not bool(state.get("_analysis_exported", False)):
        return True
    snapshot_artifacts = state.get("_snapshot_artifact_cache")
    if _has_ephemeral_value(snapshot_artifacts) and not bool(state.get("_analysis_exported", False)):
        return True
    return False


def _log_safe_failure(stage: str, error: BaseException) -> str:
    """Log only exception type and code locations, never values or messages."""

    frames = []
    traceback = error.__traceback__
    while traceback is not None:
        code = traceback.tb_frame.f_code
        frames.append(f"{code.co_name}:{traceback.tb_lineno}")
        traceback = traceback.tb_next
    diagnostic = f"{stage}:{type(error).__name__}:{','.join(frames)}"
    print(f"UTAIPEI_SAFE_FAILURE {diagnostic}")
    return diagnostic


def _empty_confirmation() -> CourseConfirmation:
    return CourseConfirmation(
        rows=(),
        fingerprint=fingerprint_course_rows(()),
        state=ConfirmationState.UNCONFIRMED,
        diagnostics=(
            InputDiagnostic(
                code="INPUT_CONFIRMATION_REQUIRED",
                message="尚未確認成績資料，不能作為正式審查輸入。",
            ),
        ),
    )


def _safe_source_digest(source: object, *, source_label: str = "") -> str:
    """Hash source identity without retaining its bytes or account details."""

    if isinstance(source, bytes):
        source_part = hashlib.sha256(source).hexdigest()
    elif isinstance(source, str):
        source_part = source
    else:
        source_part = ""
    payload = json.dumps(
        {"source": source_part, "source_label": str(source_label or "")},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cohort_mismatch_confirmation_key(
    source_digest: str,
    detected_cohort: str,
    selected_cohort: str,
) -> str:
    """Return a widget key scoped to one source/cohort mismatch context."""

    context = json.dumps(
        {
            "source": source_digest,
            "detected_cohort": detected_cohort,
            "selected_cohort": selected_cohort,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"cohort_mismatch_confirmation:{hashlib.sha256(context.encode('utf-8')).hexdigest()}"


def _safe_student_display(student_info: Mapping[str, Any] | None) -> dict[str, str]:
    """Keep only masked student display values in session/UI state."""

    student_info = student_info if isinstance(student_info, Mapping) else {}
    return {
        "name": mask_person_name(student_info.get("name")),
        "student_id": mask_student_id(student_info.get("student_id")),
    }


def _mark_confirmation_unconfirmed(
    confirmation: CourseConfirmation,
    *,
    code: str,
    message: str,
) -> CourseConfirmation:
    """Attach a safe blocker without copying parser diagnostics or payloads."""

    return CourseConfirmation(
        rows=confirmation.rows,
        fingerprint=confirmation.fingerprint,
        state=ConfirmationState.UNCONFIRMED,
        diagnostics=(*confirmation.diagnostics, InputDiagnostic(code=code, message=message)),
        confirmed_fingerprint=None,
    )


def _safe_parser_amount(value: object) -> str | None:
    """Return only a simple finite-looking amount from parser diagnostics."""

    text = str(value).strip() if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return text.rstrip("0").rstrip(".") if "." in text else text
    return None


def _safe_parser_count(value: object) -> int | None:
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return count if count >= 0 else None


def _safe_parser_delta(value: object) -> str | None:
    """Return a non-negative, finite-looking difference for UI text."""

    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return None
    text = text.lstrip("-")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _safe_parser_warning(value: object) -> str | None:
    """Keep only known parser-generated Chinese warnings for the student UI."""

    if not isinstance(value, str):
        return None
    message = value.strip()
    if not message or len(message) > 240 or re.search(r"[\r\n]", message):
        return None
    folded = message.casefold()
    if any(
        token.casefold() in folded
        for token in (
            "UNKNOWN",
            "DecisionSnapshot",
            "EXCLUSIVE",
            "shadow",
            "Traceback",
            "例外",
            "PRIVATE-",
        )
    ):
        return None
    if not message.startswith(("修習學分核對", "實得學分核對", "成績單出現互相衝突", "發現", "成績單含抵免")):
        return None
    return message


def _parser_diagnostic_messages(parse_diagnostics: Mapping[str, Any] | None, adapted_diagnostics: Iterable[Any] = ()) -> tuple[str, ...]:
    """Translate trusted parser flags into concrete, non-sensitive UI guidance."""

    diagnostics = parse_diagnostics if isinstance(parse_diagnostics, Mapping) else {}
    messages: list[str] = []
    reconciliation = diagnostics.get("reconciliation")
    reconciliation_status = ""
    reconciliation_detail = False
    if isinstance(reconciliation, Mapping):
        reconciliation_status = str(reconciliation.get("status") or "").strip().lower()
        if reconciliation_status not in {"conflict", "limited", "not_available"}:
            for key, title in (("attempted", "修習學分"), ("earned", "實得學分")):
                section = reconciliation.get(key)
                if not isinstance(section, Mapping) or section.get("reconciled") is not False:
                    continue
                parsed = _safe_parser_amount(section.get("parsed"))
                reported = _safe_parser_amount(section.get("reported"))
                difference = _safe_parser_delta(section.get("difference"))
                if parsed is not None and reported is not None:
                    detail = f"{title}核對結果：課程列合計 {parsed} 學分，成績單標示 {reported} 學分"
                    if difference is not None:
                        detail += f"，相差 {difference} 學分"
                    messages.append(detail + "；請確認是否漏列學期資料。")
                    reconciliation_detail = True
                elif title == "修習學分":
                    messages.append("修習學分總額尚未取得可核對的雙方數字；請確認成績單摘要。")
                    reconciliation_detail = True
                else:
                    messages.append("實得學分總額尚未取得可核對的雙方數字；請確認成績單摘要。")
                    reconciliation_detail = True
        if reconciliation_status == "conflict" and not reconciliation_detail:
            messages.append("成績單中的修習或實得總額互相衝突，無法完成學分核對；請確認原始成績單。")
        elif reconciliation_status == "limited" and not reconciliation_detail:
            messages.append("成績單含抵免／抵認資料，但缺少正式實得學分；請確認校方登載。")
        elif reconciliation_status == "not_available" and not reconciliation_detail:
            messages.append("尚未找到完整的全歷年修習與實得總額，暫不能完成學分核對。")
        elif reconciliation_status == "mismatch" and not reconciliation_detail:
            messages.append("已辨識的課程列尚未與成績單總額核對一致；請確認是否漏列學期資料。")
    elif diagnostics.get("total_reconciled") is False:
        parsed_total = _safe_parser_amount(diagnostics.get("parsed_total"))
        reported_total = _safe_parser_amount(diagnostics.get("reported_total"))
        if parsed_total is not None and reported_total is not None:
            messages.append(
                f"已辨識課程列合計 {parsed_total} 學分，但成績單標示總額為 {reported_total} 學分；請確認是否漏列學期資料。"
            )
        else:
            messages.append("已辨識的課程列尚未與成績單總額核對一致；請確認是否漏列學期資料。")
    fatal_warnings = diagnostics.get("fatal_warnings")
    if isinstance(fatal_warnings, (list, tuple, set, frozenset)):
        for item in fatal_warnings:
            warning = _safe_parser_warning(item)
            if warning and warning not in messages:
                messages.append(warning)
    if diagnostics.get("complete") is False:
        missing_fields = diagnostics.get("missing_fields")
        if isinstance(missing_fields, (list, tuple, set, frozenset)) and missing_fields:
            messages.append("成績單基本欄位尚未完整辨識，請逐列檢視後再確認。")
        elif not messages:
            messages.append("成績單解析尚未完整，請逐列檢視或改用其他來源。")
    if diagnostics.get("department_detected") is False:
        messages.append("尚未辨識主修系所／組別；主修分類需要人工核對。")
    course_code_missing = _safe_parser_count(diagnostics.get("course_code_missing"))
    if course_code_missing:
        messages.append(
            f"有 {course_code_missing} 門課未提供課號；已能依課程名稱與學分核對的課程可照常處理，"
            "只有需要精確身分辨識的規則才需人工確認。"
        )
    department_missing = _safe_parser_count(diagnostics.get("offering_department_missing"))
    if department_missing:
        messages.append(
            f"有 {department_missing} 門課未提供開課系所；已能依課程名稱與學分核對的課程可照常處理，"
            "跨系同名或需要系所條件的規則才需人工確認。"
        )
    if diagnostics.get("identity_warnings"):
        messages.append("部分課程身分欄位尚未完整，請在確認表補齊可核對資料。")
    if diagnostics.get("warnings") and not messages:
        messages.append("成績單部分欄位尚待核對，請檢視確認表中的提示。")
    for item in adapted_diagnostics:
        message = getattr(item, "message", None)
        if isinstance(message, str) and message.strip():
            cleaned = message.strip()
            folded = cleaned.casefold()
            if any(
                token.casefold() in folded
                for token in ("UNKNOWN", "DecisionSnapshot", "EXCLUSIVE", "shadow", "Traceback")
            ):
                continue
            if cleaned not in messages:
                messages.append(cleaned)
    return tuple(messages)


def _parser_confirmation(sidebar_state: Mapping[str, Any]) -> CourseConfirmation:
    """Parse current PDF/portal input and create or reuse parsed confirmation."""

    source = st.session_state.get("transcript_pdf_bytes") or st.session_state.get("transcript_pdf_path")
    if not source:
        st.session_state["_student_display"] = {"name": "＊＊", "student_id": "••••"}
        st.session_state.pop("_parser_confirmation_cohort", None)
        return _empty_confirmation()

    source_digest = _safe_source_digest(source, source_label=sidebar_state.get("source_label", ""))
    selected_cohort = str(sidebar_state.get("admission_cohort") or "").strip()
    cached_digest = st.session_state.get("_source_fingerprint")
    cached_cohort = str(st.session_state.get("_parser_confirmation_cohort") or "").strip()
    cached_confirmation = st.session_state.get("_parsed_confirmation")
    cached_has_cohort_blocker = bool(
        isinstance(cached_confirmation, CourseConfirmation)
        and any(item.code == "COHORT_MISMATCH" for item in cached_confirmation.diagnostics)
    )
    # The selected handbook/cohort is part of the parser confirmation context.
    # A source digest alone is insufficient: the same transcript can be
    # confirmed under one cohort and then accidentally reused after settings
    # switch to another cohort with different rules.
    if (
        cached_digest == source_digest
        and cached_cohort == selected_cohort
        and isinstance(cached_confirmation, CourseConfirmation)
        and not cached_has_cohort_blocker
    ):
        return cached_confirmation

    try:
        student_info, courses = parse_transcript_pdf(source)
        try:
            from pdf_parser import transcript_to_markdown
            st.session_state["_transcript_markdown"] = transcript_to_markdown(courses, student_info)
        except Exception:
            st.session_state["_transcript_markdown"] = ""
        adapted = adapt_legacy_result(courses, source_kind="transcript")
        confirmation = adapted.confirmation
        st.session_state["_student_display"] = _safe_student_display(student_info)
        parse_diagnostics = student_info.get("parse_diagnostics", {}) if isinstance(student_info, Mapping) else {}
        parser_has_fatal_issue = bool(
            isinstance(parse_diagnostics, Mapping)
            and (
                parse_diagnostics.get("complete") is False
                or parse_diagnostics.get("fatal") is True
                or parse_diagnostics.get("fatal_warnings")
            )
        )
        if parser_has_fatal_issue:
            confirmation = _mark_confirmation_unconfirmed(
                confirmation,
                code="PARSER_INCOMPLETE",
                message="成績單解析尚未完整，請逐列檢視或改用其他來源。",
            )
        detected_cohort = ""
        if isinstance(parse_diagnostics, Mapping):
            detected_cohort = str(parse_diagnostics.get("detected_admission_cohort") or "").strip()
        detected_cohort = detected_cohort or (
            str(student_info.get("admission_cohort") or "").strip() if isinstance(student_info, Mapping) else ""
        )
        if detected_cohort and selected_cohort and detected_cohort != selected_cohort:
            st.warning(
                f"成績資料辨識為 {detected_cohort} 學年度，與目前選定 {selected_cohort} 學年度手冊不同；"
                "請核對規則後再繼續。"
            )
            mismatch_confirmed = st.checkbox(
                "我已核對適用規定，仍使用目前選定手冊",
                value=bool(sidebar_state.get("cohort_mismatch_confirmed", False)),
                key=_cohort_mismatch_confirmation_key(source_digest, detected_cohort, selected_cohort),
            )
            if not mismatch_confirmed:
                confirmation = _mark_confirmation_unconfirmed(
                    confirmation,
                    code="COHORT_MISMATCH",
                    message="成績資料與選定入學 cohort 不一致，需人工確認。",
                )
        st.session_state["_parser_diagnostics"] = _parser_diagnostic_messages(parse_diagnostics, adapted.diagnostics)
    except Exception as error:
        # Never expose parser details or retain the parser's student record.
        st.session_state["_student_display"] = {"name": "＊＊", "student_id": "••••"}
        st.session_state["_parser_diagnostics"] = (_safe_error_message(error),)
        confirmation = _empty_confirmation()

    if (
        isinstance(cached_confirmation, CourseConfirmation)
        and cached_digest not in (None, source_digest)
        and cached_confirmation.state is ConfirmationState.CONFIRMED
    ):
        confirmation = CourseConfirmation(
            rows=confirmation.rows,
            fingerprint=confirmation.fingerprint,
            state=ConfirmationState.STALE,
            diagnostics=(
                *confirmation.diagnostics,
                InputDiagnostic(code="SOURCE_CHANGED", message="來源資料已變更，請重新檢視並確認。"),
            ),
            confirmed_fingerprint=cached_confirmation.confirmed_fingerprint,
        )

    # Any source change creates a new parsed state and invalidates a prior
    # confirmation.  The stored object contains normalized scalar rows only.
    st.session_state["_source_fingerprint"] = source_digest
    st.session_state["_parser_confirmation_cohort"] = selected_cohort
    st.session_state["_parsed_confirmation"] = confirmation
    st.session_state["_editor_rows"] = tuple(row.as_dict() for row in confirmation.rows)
    st.session_state["_analysis_exported"] = False
    return confirmation


def _as_editor_records(value: object) -> tuple[Mapping[str, Any], ...] | None:
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, (str, bytes, bytearray)) or value is None:
        return None
    if hasattr(value, "to_dict"):
        try:
            value = value.to_dict("records")
        except TypeError:
            return None
    if not isinstance(value, Iterable):
        return None
    return tuple(item for item in value if isinstance(item, Mapping))


_EDITOR_STATUS_LABELS = {
    "COMPLETED": "已修畢",
    "PASS": "已修畢",
    "IN_PROGRESS": "修習中",
    "FAILED": "不及格",
    "FAIL": "不及格",
    "WITHDRAWN": "停修／撤選",
    "NOT_TAKEN": "未修課",
    "NOT_ATTEMPTED": "未修課",
    "WAIVED": "免修／抵認",
    "TRANSFERRED": "抵免／抵認",
    "UNKNOWN": "需要補資料",
}
_EDITOR_STATUS_CODES = {
    label: code
    for code, label in _EDITOR_STATUS_LABELS.items()
    if code not in {"PASS", "FAIL", "NOT_ATTEMPTED"}
}
_EDITOR_STATUS_CODES.update({"已修畢": "COMPLETED", "不及格": "FAILED", "未修課": "NOT_TAKEN"})


def _preview_number(value: object, *, fallback: str = "—") -> str:
    """Format one normalized finite number for the import-only preview."""

    if isinstance(value, bool):
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    if not math.isfinite(number) or number < 0:
        return fallback
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _preview_text(value: object, *, fallback: str = "—") -> str:
    """Escape one scalar normalized field before putting it in HTML."""

    if isinstance(value, bool):
        return _escape_html(fallback)
    text = str(value).strip() if isinstance(value, (str, int, float)) else ""
    return _escape_html(text or fallback)


def _imported_course_preview_markup(confirmation: CourseConfirmation | object) -> str:
    """Build a static, safe course table for data that is not formally released.

    This projection deliberately accepts only ``NormalizedCourseRow`` fields.
    It is a review aid for parsed or edited input, so it never contains
    attempt grouping, parser payloads, student identity, or graduation status.
    """

    raw_rows = getattr(confirmation, "rows", ())
    rows = tuple(row for row in raw_rows if isinstance(row, NormalizedCourseRow))
    state = getattr(getattr(confirmation, "state", None), "value", "")
    valid = bool(getattr(confirmation, "valid", False))
    state_key = str(state or "UNCONFIRMED").strip().upper()
    released_rows = (
        release_formal_attempts(confirmation, confirmation.fingerprint)
        if isinstance(confirmation, CourseConfirmation)
        else ()
    )
    formally_released = bool(released_rows)
    if state_key == ConfirmationState.STALE.value:
        next_action = "來源資料已變更，請重新檢視並確認課程列；目前僅供核對。"
    elif not valid:
        next_action = "資料列仍需修正或補齊後才能確認；目前僅供核對。"
    elif state_key == ConfirmationState.CONFIRMED.value and not formally_released:
        next_action = "確認內容已變更或尚未固定，請重新檢視並確認；目前僅供核對。"
    elif state_key != ConfirmationState.CONFIRMED.value:
        next_action = "請檢視課程列並按「確認目前成績列」；目前僅供核對。"
    else:
        next_action = "課程列已確認，正式分析會使用這份固定資料。"

    earned_total = sum(
        float(row.earned_credits)
        for row in rows
        if isinstance(row.earned_credits, (int, float))
        and not isinstance(row.earned_credits, bool)
        and math.isfinite(float(row.earned_credits))
    )
    row_count = len(rows)
    earned_display = _preview_number(earned_total) if rows else "需要補資料"
    earned_attribute = _preview_number(earned_total) if rows else ""
    preview_state = "confirmed" if formally_released else "pending"
    headers = ("課名", "課號", "學期", "課程學分", "實得學分", "狀態")
    header_html = "".join(
        f"<th scope='col' style='border-bottom:1px solid #CBD5E1;padding:.55rem .6rem;text-align:start;white-space:nowrap'>{_escape_html(title)}</th>"
        for title in headers
    )
    row_html: list[str] = []
    for row in rows:
        status_key = str(row.status or "UNKNOWN").strip().upper().replace("-", "_").replace(" ", "_")
        status = _EDITOR_STATUS_LABELS.get(status_key, "需要補資料")
        cells = (
            _preview_text(row.course_name, fallback="未標示課程"),
            _preview_text(row.course_code),
            _preview_text(row.term, fallback="學期待補"),
            _preview_number(row.credits),
            _preview_number(row.earned_credits),
            _escape_html(status),
        )
        row_html.append(
            "<tr>"
            + "".join(
                f"<td style='border-bottom:1px solid #E2E8F0;padding:.55rem .6rem;text-align:start;vertical-align:top'>{cell}</td>"
                for cell in cells
            )
            + "</tr>"
        )
    if not row_html:
        row_html.append(
            "<tr><td colspan='6' style='padding:.7rem .6rem;text-align:start'>"
            "目前沒有可預覽的課程列；請重新上傳或改用手動輸入。"
            "</td></tr>"
        )
    return (
        "<section class='snapshot-import-preview' data-preview-state='"
        f"{preview_state}' data-row-count='{row_count}' data-earned-credits='{earned_attribute}'>"
        "<h2 class='snapshot-import-preview-title'>匯入課程預覽</h2>"
        f"<p class='snapshot-import-preview-summary'>已匯入 <strong>{row_count}</strong> 列課程；"
        f"解析實得學分小計 <strong>{earned_display}</strong> 學分。"
        "</p>"
        "<p class='snapshot-import-preview-note'>待確認／僅供核對；上述小計不是畢業學分，確認前不會產生正式判定。</p>"
        f"<p class='snapshot-import-preview-next-action'>{_escape_html(next_action)}</p>"
        "<div class='snapshot-import-preview-scroll' style='max-width:100%;overflow-x:auto;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch'>"
        "<table aria-label='匯入課程預覽' style='border-collapse:collapse;width:100%;min-width:46rem'>"
        f"<thead><tr>{header_html}</tr></thead><tbody>{''.join(row_html)}</tbody></table>"
        "</div></section>"
    )


def _render_imported_course_preview(confirmation: CourseConfirmation | object) -> None:
    """Render the static confirmation preview without entering formal analysis."""

    render_html(_imported_course_preview_markup(confirmation), ui=st)


def _editor_display_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Translate normalized course rows for the editable student table."""

    display_rows: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        status = str(item.get("status") or "UNKNOWN").upper().replace("-", "_")
        item["status"] = _EDITOR_STATUS_LABELS.get(status, "需要補資料")
        display_rows.append(item)
    return display_rows


def _editor_internal_records(records: Iterable[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    """Map the Chinese table values back to input_confirmation status codes."""

    internal: list[Mapping[str, Any]] = []
    for record in records:
        item = dict(record)
        status = str(item.get("status") or "需要補資料").strip()
        item["status"] = _EDITOR_STATUS_CODES.get(status, status)
        internal.append(item)
    return tuple(internal)


def _confirmation_column_config() -> dict[str, object]:
    """Return Chinese Streamlit column labels without relying on a version API."""

    config = getattr(st, "column_config", None)
    if config is None:
        return {}

    def make(name: str, title: str, **kwargs: object) -> object | None:
        factory = getattr(config, name, None)
        if factory is None:
            return None
        try:
            return factory(title, **kwargs)
        except (TypeError, ValueError):
            try:
                return factory(title)
            except (TypeError, ValueError):
                return None

    columns: dict[str, object] = {}
    for key, title in (
        ("course_code", "課程代碼"),
        ("course_name", "課程名稱"),
        ("term", "修課學期"),
        ("academic_year", "學年度"),
        ("semester", "學期"),
        ("grade", "成績"),
        ("department", "開課系所"),
        ("course_type", "課程類型"),
    ):
        column = make("TextColumn", title)
        if column is not None:
            columns[key] = column
    for key, title in (("credits", "課程學分"), ("earned_credits", "實得學分")):
        column = make("NumberColumn", title, format="%g")
        if column is not None:
            columns[key] = column
    status_column = make("SelectboxColumn", "修課狀態", options=list(dict.fromkeys(_EDITOR_STATUS_LABELS.values())))
    if status_column is None:
        status_column = make("TextColumn", "修課狀態")
    if status_column is not None:
        columns["status"] = status_column
    # Keep this identity field in the normalized rows for confirmation and
    # re-release, while keeping an opaque grouping token out of the student
    # editor's primary view.
    columns["attempt_group"] = None
    return columns


def _render_confirmation_editor(confirmation: CourseConfirmation) -> CourseConfirmation:
    """Render normalized rows and return the current lifecycle state."""

    display = st.session_state.get("_student_display")
    if isinstance(display, Mapping):
        st.caption(f"成績資料：{display.get('name', '＊＊')}／學號 {display.get('student_id', '••••')}（預設遮罩）")
    diagnostics = tuple(
        item.strip()
        for item in st.session_state.get("_parser_diagnostics", ())
        if isinstance(item, str) and item.strip()
    )
    if diagnostics:
        st.warning("成績資料尚有待確認項目，請檢視下方列資料後再確認。")
        with st.expander("查看解析核對原因", expanded=True):
            for message in diagnostics:
                st.write(f"• {message}")

    if st.session_state.get("_transcript_markdown"):
        st.markdown(st.session_state["_transcript_markdown"], unsafe_allow_html=True)

    current = confirmation
    editor_rows = _editor_display_rows(row.as_dict() for row in confirmation.rows)
    if editor_rows:
        try:
            edited = st.data_editor(
                editor_rows,
                key="transcript_rows_editor",
                hide_index=True,
                num_rows="dynamic",
                use_container_width=True,
                disabled=["attempt_group"],
                column_config=_confirmation_column_config(),
            )
            records = _as_editor_records(edited)
            current_records = tuple(row.as_dict() for row in current.rows)
            internal_records = _editor_internal_records(records) if records is not None else None
            if internal_records is not None and internal_records != current_records:
                current = edit_confirmation(current, internal_records)
        except (AttributeError, TypeError, ValueError):
            # A missing editor keeps the formal release gate closed.
            current = confirmation
    else:
        st.info("目前沒有可供確認的課程列；請重新上傳或改用手動輸入。")

    if current.state is ConfirmationState.CONFIRMED:
        st.success("目前課程列已確認；若修改任何欄位，必須重新確認。")
    else:
        if current.state is ConfirmationState.STALE:
            st.warning("課程列在上次確認後已變更，請重新檢視並確認。")
        elif current.state is ConfirmationState.UNCONFIRMED:
            st.warning("課程列尚未通過安全檢查，不能產生正式通過判定。")
        # Parser fatal diagnostics make ``valid`` false.  Keep the button in
        # the same place so the user can see the next step, but make the
        # unsafe action impossible until there are rows without diagnostics.
        if st.button(
            "確認目前成績列",
            type="primary",
            use_container_width=True,
            key="confirm_transcript_rows",
            disabled=not (current.valid and bool(current.rows)),
        ):
            confirmed = confirm_confirmation(current, current.fingerprint)
            if confirmed.state is ConfirmationState.CONFIRMED:
                current = confirmed
                st.success("已確認目前課程列；後續分析將使用這份固定指紋。")
            else:
                st.warning("目前課程列仍有待確認資料，請先修正或補齊。")

    st.session_state["_parsed_confirmation"] = current
    st.session_state["_editor_rows"] = tuple(row.as_dict() for row in current.rows)
    return current


def _confirmed_rows(confirmation: object) -> tuple[Any, ...]:
    """Release only rows protected by the exact confirmation fingerprint."""

    if not isinstance(confirmation, CourseConfirmation):
        return ()
    return release_formal_attempts(confirmation, confirmation.fingerprint)


def _build_evaluation_request(
    sidebar_state: Mapping[str, Any],
    confirmation: CourseConfirmation | object | None = None,
    *,
    released_rows: Iterable[Any] | None = None,
) -> EvaluationRequest:
    """Build the privacy-safe service request from settings and formal rows."""

    confirmation = confirmation if isinstance(confirmation, CourseConfirmation) else None
    state = confirmation.state.value if confirmation is not None else "UNCONFIRMED"
    fingerprint = confirmation.fingerprint if confirmation is not None else ""
    released = _confirmed_rows(confirmation) if released_rows is None else tuple(released_rows)
    transcript_confirmed = bool(
        confirmation is not None
        and confirmation.state is ConfirmationState.CONFIRMED
        and confirmation.valid
        and confirmation.confirmed_fingerprint == fingerprint
    )
    primary_id = sidebar_state.get("primary_curriculum_id") or ""
    target_id = sidebar_state.get("target_curriculum_id")
    target_candidate = sidebar_state.get("target_curriculum_version_candidate") or target_id
    return EvaluationRequest(
        admission_cohort=str(sidebar_state.get("admission_cohort") or ""),
        primary_curriculum_id=str(primary_id),
        confirmed_course_rows=tuple(released),
        confirmed_course_fingerprint=fingerprint,
        transcript_confirmed=transcript_confirmed,
        confirmation_state=state,
        program_type=str(sidebar_state.get("program_type") or "單主修"),
        secondary_kind=sidebar_state.get("secondary_kind"),
        target_curriculum_id=str(target_id) if target_id else None,
        target_curriculum_version_candidate=str(target_candidate) if target_candidate else None,
        target_curriculum_year=sidebar_state.get("target_curriculum_year"),
        target_program=sidebar_state.get("target_program"),
        target_track=sidebar_state.get("target_track"),
        application_year=sidebar_state.get("application_year"),
        application_semester=sidebar_state.get("application_semester"),
        application_status=sidebar_state.get("application_self_report") or sidebar_state.get("application_status"),
        school_approval_status=sidebar_state.get("school_approval_self_report") or sidebar_state.get("school_approval_status"),
        formal_qualification_status=(
            sidebar_state.get("formal_qualification_self_report")
            or sidebar_state.get("formal_qualification_status")
        ),
        formal_award_status=sidebar_state.get("formal_award_self_report") or sidebar_state.get("formal_award_status"),
        input_warning_codes=tuple(sidebar_state.get("input_warning_codes", ())),
    )


def _render_snapshot_outputs(snapshot: object) -> None:
    """Render one snapshot and build exports only after an explicit action."""

    try:
        render_snapshot, build_pdf, build_allocation_csv, build_audit_json = _load_presentation_api()
    except (ImportError, ModuleNotFoundError):
        st.info("報表元件尚在載入，分析快照已保留；請稍後重新整理。")
        return

    artifacts = _snapshot_artifact_cache(snapshot)
    rendered_html = artifacts.get("rendered_html")
    if rendered_html is None:
        try:
            rendered_html = render_snapshot(snapshot)
        except Exception as error:
            _log_safe_failure("snapshot-render", error)
            st.error("分析資料暫時無法轉為報表；固定分析快照仍保留，請重新整理後再試。")
            return
        artifacts["rendered_html"] = rendered_html
    try:
        # The report is already complete, sanitized HTML.  Sending it through
        # Markdown can terminate a raw-HTML block at embedded chart boundaries
        # and silently drop later charts and requirement expanders.
        render_html(
            _report_export_state(str(rendered_html), bool(st.session_state.get("_analysis_exported", False))),
            ui=st,
        )
    except Exception as error:
        _log_safe_failure("snapshot-html", error)
        st.error("分析報表暫時無法顯示；固定分析快照仍保留，請重新整理後再試。")
        return

    if not bool(st.session_state.get("_exports_ready", False)):
        prepare = st.button(
            "準備匯出檔案",
            use_container_width=True,
            key="prepare_snapshot_exports",
            help="只有按下後才會建立 PDF、CSV 與稽核摘要，減少每次畫面重整的等待時間。",
        )
        if not prepare:
            st.caption("需要檔案時再按「準備匯出檔案」；報表畫面不會預先建立匯出檔。")
            return
        st.session_state["_exports_ready"] = True

    downloads = (
        ("pdf", "下載列印 PDF", build_pdf, "utaipei-graduation-report.pdf", "application/pdf"),
        ("csv", "下載課程配置 CSV", build_allocation_csv, "utaipei-allocation.csv", "text/csv"),
        ("audit", "下載規則與判定摘要", build_audit_json, "utaipei-audit.json", "application/json"),
    )
    export_cache = artifacts.setdefault("exports", {})
    for export_key, label, builder, filename, mime in downloads:
        try:
            if export_key not in export_cache:
                export_cache[export_key] = builder(snapshot)
            payload = export_cache[export_key]
            clicked = st.download_button(
                label,
                data=payload,
                file_name=filename,
                mime=mime,
                use_container_width=True,
            )
        except Exception as error:
            _log_safe_failure(f"snapshot-export:{filename}", error)
            st.error(f"{label.replace('下載', '')}暫時無法建立；畫面仍使用同一份固定分析快照。")
            continue
        if clicked:
            st.session_state["_analysis_exported"] = True


def _render_analysis_state_marker(*, active: bool | None = None) -> None:
    # ``active`` remains a compatibility hint for callers/tests, while the
    # session scan is authoritative so a raw or pending input cannot be missed.
    has_ephemeral_state = _has_ephemeral_student_state()
    active_state = has_ephemeral_state if active is None else bool(active) or has_ephemeral_state
    exported = bool(st.session_state.get("_analysis_exported", False))
    render_html(
        f"<div id='utaipei-analysis-state' data-analysis-active='{str(active_state).lower()}' "
        f"data-exported='{str(exported).lower()}'></div>",
        ui=st,
    )


def main(*, show_entrance=False):
    setup_page()
    if show_entrance:
        from welcome import render_entrance

        if not render_entrance():
            return
    render_header_card("北市大畢業通", "依入學年度規劃畢業、輔系與雙主修", landmark_id="main-content")
    sidebar_state = render_setup_panel()
    collapse_sidebar_if_needed()

    confirmation = _parser_confirmation(sidebar_state)
    has_source = bool(sidebar_state.get("has_transcript"))
    if has_source:
        confirmation = _render_confirmation_editor(confirmation)

    if not has_source:
        _clear_snapshot_caches()
        _render_analysis_state_marker(active=False)
        st.info("完成上方設定後，請上傳歷年成績單 PDF，或使用校務系統帳密即時抓取；確認資料後這裡會顯示學分進度。")
        return

    # Parsed, stale, invalid, or fingerprint-mismatched rows are useful for
    # review but are not formal attempts.  Keep them visible in a static
    # preview while clearing any previous snapshot and stopping before the
    # service boundary.  A released zero-credit course is still a real row,
    # so the non-empty check intentionally uses the released tuple only.
    released_rows = _confirmed_rows(confirmation)
    if not released_rows:
        _clear_snapshot_caches()
        _render_imported_course_preview(confirmation)
        _render_analysis_state_marker(active=True)
        return

    primary_id = str(sidebar_state.get("primary_curriculum_id") or "")
    if not primary_id or primary_id in {f"primary:{year}:math" for year in ("113", "114", "115")}:
        _clear_snapshot_caches()
        _render_analysis_state_marker(active=False)
        st.info("請完成主修設定；數學系 113 學年度起須選擇主修專業領域，再按「套用設定」。")
        return

    request = _build_evaluation_request(sidebar_state, confirmation, released_rows=released_rows)

    # This is intentionally the only production evaluation call in this file.
    try:
        snapshot = _evaluate_cached_snapshot(request)
    except Exception as error:
        st.error(_safe_error_message(error))
        _render_analysis_state_marker(active=False)
        return

    try:
        _render_snapshot_outputs(snapshot)
    except Exception as error:
        st.error(_safe_error_message(error))
    _render_analysis_state_marker(active=bool(has_source and (confirmation.rows or released_rows)))


if __name__ == "__main__":
    main(show_entrance=True)
