"""北市大畢業通 Streamlit entrypoint.

The page has one evaluation boundary: parser/crawler rows are confirmed by
the user, ``graduation_service.evaluate`` creates a ``DecisionSnapshot``, and
presentation/export functions consume that same object.  No legacy evaluator
is used here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

import streamlit as st

from course_input_adapter import adapt_legacy_result
from graduation_service import EvaluationRequest, evaluate
from input_confirmation import (
    ConfirmationState,
    CourseConfirmation,
    InputDiagnostic,
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

    from snapshot_exports import build_allocation_csv, build_audit_json, build_pdf
    from snapshot_renderer import render_snapshot

    return render_snapshot, build_pdf, build_allocation_csv, build_audit_json


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


def _parser_confirmation(sidebar_state: Mapping[str, Any]) -> CourseConfirmation:
    """Parse current PDF/portal input and create or reuse parsed confirmation."""

    source = st.session_state.get("transcript_pdf_bytes") or st.session_state.get("transcript_pdf_path")
    if not source:
        st.session_state["_student_display"] = {"name": "＊＊", "student_id": "••••"}
        return _empty_confirmation()

    source_digest = _safe_source_digest(source, source_label=sidebar_state.get("source_label", ""))
    cached_digest = st.session_state.get("_source_fingerprint")
    cached_confirmation = st.session_state.get("_parsed_confirmation")
    cached_has_cohort_blocker = bool(
        isinstance(cached_confirmation, CourseConfirmation)
        and any(item.code == "COHORT_MISMATCH" for item in cached_confirmation.diagnostics)
    )
    if cached_digest == source_digest and isinstance(cached_confirmation, CourseConfirmation) and not cached_has_cohort_blocker:
        return cached_confirmation

    try:
        student_info, courses = parse_transcript_pdf(source)
        adapted = adapt_legacy_result(courses, source_kind="transcript")
        confirmation = adapted.confirmation
        st.session_state["_student_display"] = _safe_student_display(student_info)
        parse_diagnostics = student_info.get("parse_diagnostics", {}) if isinstance(student_info, Mapping) else {}
        if isinstance(parse_diagnostics, Mapping) and parse_diagnostics.get("complete") is False:
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
        selected_cohort = str(sidebar_state.get("admission_cohort") or "").strip()
        if detected_cohort and selected_cohort and detected_cohort != selected_cohort:
            st.warning(
                f"成績資料辨識為 {detected_cohort} 學年度，與目前選定 {selected_cohort} 學年度手冊不同；"
                "請核對規則後再繼續。"
            )
            mismatch_confirmed = st.checkbox(
                "我已核對適用規定，仍使用目前選定手冊",
                value=bool(sidebar_state.get("cohort_mismatch_confirmed", False)),
                key="cohort_mismatch_confirmation",
            )
            if not mismatch_confirmed:
                confirmation = _mark_confirmation_unconfirmed(
                    confirmation,
                    code="COHORT_MISMATCH",
                    message="成績資料與選定入學 cohort 不一致，需人工確認。",
                )
        if adapted.diagnostics:
            st.session_state["_parser_diagnostics"] = tuple(item.message for item in adapted.diagnostics)
        else:
            st.session_state["_parser_diagnostics"] = ()
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


def _render_confirmation_editor(confirmation: CourseConfirmation) -> CourseConfirmation:
    """Render normalized rows and return the current lifecycle state."""

    display = st.session_state.get("_student_display")
    if isinstance(display, Mapping):
        st.caption(f"成績資料：{display.get('name', '＊＊')}／學號 {display.get('student_id', '••••')}（預設遮罩）")
    diagnostics = st.session_state.get("_parser_diagnostics", ())
    if diagnostics:
        st.warning("成績資料尚有待確認項目，請檢視下方列資料後再確認。")

    current = confirmation
    editor_rows = [row.as_dict() for row in confirmation.rows]
    if editor_rows:
        try:
            edited = st.data_editor(
                editor_rows,
                key="transcript_rows_editor",
                hide_index=True,
                num_rows="dynamic",
                use_container_width=True,
                disabled=["attempt_group"],
            )
            records = _as_editor_records(edited)
            current_records = tuple(row.as_dict() for row in current.rows)
            if records is not None and tuple(dict(record) for record in records) != current_records:
                current = edit_confirmation(current, records)
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
        if st.button("確認目前成績列", type="primary", use_container_width=True, key="confirm_transcript_rows"):
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


def _render_official_decisions(snapshot: object) -> None:
    decisions = getattr(snapshot, "decisions", {})
    if not isinstance(decisions, Mapping):
        return
    st.markdown("### 官方判定（來自同一份分析快照）")
    labels = [("primary_graduation", "主修畢業")]
    optional_groups = (
        (
            "double_major_qualification",
            (
                ("double_major_qualification", "雙主修資格"),
                ("formal_double_major_award", "正式授予雙主修"),
            ),
        ),
        (
            "minor_application_or_qualification",
            (
                ("minor_application_or_qualification", "輔系申請／資格"),
                ("minor_coursework_completion", "輔系課程完成度"),
                ("formal_minor_award", "正式授予輔系"),
            ),
        ),
    )
    for sentinel, group in optional_groups:
        item = decisions.get(sentinel, {})
        status = item.get("status", "UNKNOWN") if isinstance(item, Mapping) else "UNKNOWN"
        if status != "NOT_APPLICABLE":
            labels.extend(group)
    labels.append(("overall", "整體結果"))
    for key, label in labels:
        item = decisions.get(key, {})
        status = item.get("status", "UNKNOWN") if isinstance(item, Mapping) else "UNKNOWN"
        st.write(f"{label}：{status}")


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


def main():
    setup_page()
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

    released_rows = _confirmed_rows(confirmation)
    request = _build_evaluation_request(sidebar_state, confirmation, released_rows=released_rows)

    # This is intentionally the only production evaluation call in this file.
    try:
        snapshot = _evaluate_cached_snapshot(request)
    except Exception as error:
        st.error(_safe_error_message(error))
        _render_analysis_state_marker(active=False)
        return

    _render_official_decisions(snapshot)
    try:
        _render_snapshot_outputs(snapshot)
    except Exception as error:
        st.error(_safe_error_message(error))
    _render_analysis_state_marker(active=bool(has_source and (confirmation.rows or released_rows)))


if __name__ == "__main__":
    main()
