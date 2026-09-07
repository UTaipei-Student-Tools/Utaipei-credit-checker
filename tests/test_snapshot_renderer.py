from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from allocation_engine import (
    COMPLETE,
    VERIFIED,
    AllocationResult,
    AttemptAllocation,
    CourseAttempt,
    CreditPortion,
    RequirementResult,
    RequirementSpec,
)
from decision_snapshot import DecisionSnapshot, build_decision_snapshot
from snapshot_renderer import build_snapshot_projection, render_snapshot


def _snapshot() -> DecisionSnapshot:
    snapshot = build_decision_snapshot(
        {
            "attempts": (
                CourseAttempt("a", "A-001", "核心課程", Decimal("3"), Decimal("3"), "114-1", status="PASS"),
                CourseAttempt("b", "B-001", "修習中課程", Decimal("2"), Decimal("0"), "115-1", status="IN_PROGRESS"),
            ),
            "requirements": (
                RequirementSpec(
                    "req-core",
                    "系必修核心",
                    Decimal("3"),
                    eligible_course_ids=("A-001",),
                    coverage_state=COMPLETE,
                    evidence_state=VERIFIED,
                    bucket="required",
                    kind="必修",
                ),
                RequirementSpec(
                    "req-unknown",
                    "資料不足課程池",
                    Decimal("2"),
                    eligible_course_ids=("B-001",),
                    coverage_state="PARTIAL",
                    evidence_state=VERIFIED,
                    bucket="elective",
                    kind="選修",
                ),
            ),
            "input_confirmation": {
                "state": "CONFIRMED",
                "current_fingerprint": "renderer-fixture",
                "confirmed_fingerprint": "renderer-fixture",
                "formal_release_success": True,
                "row_count": 2,
                "released_row_count": 2,
            },
        },
        evaluated_at="2026-09-02T00:00:00Z",
    )
    allocation = AllocationResult(
        status="UNKNOWN",
        allocations=(
            AttemptAllocation("a", Decimal("3"), (CreditPortion("a", "req-core", Decimal("3")),), Decimal("0")),
            AttemptAllocation("b", Decimal("0"), (), Decimal("0")),
        ),
        requirement_results=(
            RequirementResult("req-core", "PASS", Decimal("3"), Decimal("3"), Decimal("0"), Decimal("3"), Decimal("0"), "COMPLETE", "VERIFIED"),
            RequirementResult("req-unknown", "UNKNOWN", Decimal("2"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("2"), "PARTIAL", "VERIFIED", blockers=("待確認",)),
        ),
        source_earned_credits=Decimal("3"),
        recognized_credits=Decimal("3"),
        unallocated_credits=Decimal("0"),
        credit_conservation=True,
        alternative_allocations=(("a", (("req-core", "3", "EXCLUSIVE", "", ""),), "0"),),
    )
    return replace(
        snapshot,
        allocation=allocation,
        snapshot_id="snapshot:renderer-fixture",
        verdict="UNKNOWN",
        decisions={
            "primary_graduation": {"status": "UNKNOWN", "reason": "仍有待核對規則"},
            "double_major_qualification": {"status": "NOT_APPLICABLE", "reason": "目前不是雙主修"},
            "formal_double_major_award": {"status": "NOT_APPLICABLE"},
            "overall": {"status": "UNKNOWN", "reason": "需要人工確認"},
        },
        rule_provenance=(
            {
                "requirement_id": "req-core",
                "source_reference": "official:handbook:114:p.10",
                "source_location": "PDF p.10 表一",
                "coverage_state": "COMPLETE",
                "evidence_state": "VERIFIED",
                "automatic_decision": True,
            },
        ),
        statistics={
            "total_graduation_credits": "128",
            "recognized_credits": "3",
            "effective_recognized_credits": "3",
            "unallocated_credits": "0",
            "shared_shadow_credits": "0",
            "credit_conservation": True,
            "by_bucket": {"required": "3", "elective": "0", "general_education": "0", "free": "0"},
            "requirement_status_counts": {"PASS": 1, "UNKNOWN": 1},
            "course_status_counts": {"PASS": 1, "IN_PROGRESS": 1},
            "completed": 1,
            "in_progress": 1,
            "unresolved": 0,
            "deficits": ({"requirement_id": "req-unknown", "name": "資料不足課程池", "deficit": "2", "status": "UNKNOWN"},),
            "shortest_safe_remediation": ("資料不足課程池 的缺額或課程池仍需人工確認。",),
        },
        blockers=("RULE_CONTEXT:MANUAL_REVIEW",),
        warnings=("課程池仍需人工確認",),
        remediation_suggestions=("資料不足課程池 的缺額或課程池仍需人工確認。",),
    )


def test_renderer_calls_as_dict_once_and_exposes_stable_snapshot_id(monkeypatch):
    snapshot = _snapshot()
    original = DecisionSnapshot.as_dict
    calls = 0

    def counted(self):
        nonlocal calls
        calls += 1
        return original(self)

    monkeypatch.setattr(DecisionSnapshot, "as_dict", counted)
    output = render_snapshot(snapshot)

    assert calls == 1
    assert snapshot.snapshot_id in output
    assert 'data-snapshot-id="' in output
    assert "資料不足／需人工確認" in output


def test_snapshot_projection_contains_requirement_expanders_and_course_explanations():
    snapshot = _snapshot()
    projection = build_snapshot_projection(snapshot)
    assert projection["snapshot_id"] == snapshot.snapshot_id
    assert projection["requirements"]
    unknown = next(item for item in projection["requirements"] if item["requirement_id"] == "req-unknown")
    assert unknown["coverage_state"] == "PARTIAL"
    assert "需人工確認" in unknown["manual_confirmation"]

    output = render_snapshot(snapshot)
    assert output.count('id="graduation-standard-check"') == 1
    assert output.index("畢業標準檢核") < output.index("行政資訊")
    assert '<details class="snapshot-requirement-expander"' in output
    assert 'data-requirement-id="req-core"' in output
    assert "核心課程" in output
    assert "本要求採計" in output
    assert "採計原因" not in output
    assert "採計用途" in output
    assert "原因" in output
    assert "規則來源" in output
    assert "其他可行方式" in output
    assert "沒有其他安全路徑" in output or "資料不足" in output
    assert "min-width" not in output
    assert "height:" not in output.replace("line-height:", "")


def test_renderer_exposes_v2_statistics_digest_and_fail_closed_chart_contract():
    projection = build_snapshot_projection(_snapshot())
    output = render_snapshot(_snapshot())

    assert projection["statistics_schema"] == "decision-statistics.v2"
    assert projection["statistics_digest"] == projection["statistics"]["statistics_digest"]
    assert projection["chart_datasets"]["statistics_digest"] == projection["statistics_digest"]
    assert 'data-statistics-schema="decision-statistics.v2"' in output
    assert f'data-statistics-digest="{projection["statistics_digest"]}"' in output
    assert 'data-chart-id="F11"' in output
    assert "AGGREGATE_GATE_UNAVAILABLE" not in output
    assert "建議下一步" in output
    assert "DIRECTION_ONLY" not in output
    assert projection["presentation_warnings"]
    assert "呈現提醒" in output


def test_renderer_exposes_distinct_course_and_requirement_count_units():
    projection = build_snapshot_projection(_snapshot())
    summary = projection["summary"]

    assert summary["course_counts"]["PASS"] == 1
    assert summary["course_counts"]["IN_PROGRESS"] == 1
    assert summary["requirement_counts"]["PASS"] == 1
    assert summary["requirement_counts"]["UNKNOWN"] == 1
    assert summary["course_counts"] != summary["requirement_counts"]
    output = render_snapshot(_snapshot())
    assert "有效學分" in output
    assert "必修進度" in output


def test_renderer_uses_semantic_tables_for_courses_and_credit_categories():
    output = render_snapshot(_snapshot())

    assert '<table class="snapshot-course-options"' in output
    assert '<table class="snapshot-course-list"' in output
    assert '<table class="snapshot-simple-list snapshot-credit-category-table"' in output
    assert '<table class="snapshot-simple-list snapshot-credit-summary-table"' in output
    assert '<th scope="col">課名</th>' in output
    assert '<th scope="col">學期</th>' in output
    assert '<th scope="col">修得學分</th>' in output
    assert '<th scope="col">此類採計學分</th>' in output
    assert '<th scope="col">狀態／備註</th>' in output
    assert '<div class="snapshot-table-scroll">' in output
    assert '<ul class="snapshot-course-list"' not in output
    assert '<ul class="snapshot-course-options"' not in output
    assert 'class="snapshot-course"' in output


def test_renderer_keeps_source_earned_separate_from_effective_credits(monkeypatch):
    snapshot = _snapshot()
    import snapshot_renderer

    original_projection = snapshot_renderer.build_snapshot_projection

    def source_and_effective_are_distinct(value):
        projection = dict(original_projection(value))
        summary = dict(projection["summary"])
        summary.update(
            {
                "source_earned_credits": "87",
                "counted_exclusive_credits": "70",
                "recognized_credits": "70",
                "effective_recognized_credits": "70",
            }
        )
        projection["summary"] = summary
        return projection

    monkeypatch.setattr(snapshot_renderer, "build_snapshot_projection", source_and_effective_are_distinct)
    output = render_snapshot(snapshot)

    assert "成績單實得學分：87 學分" in output
    assert '<th scope="row">成績單實得學分</th><td><strong>87 學分</strong></td>' in output
    assert '<th scope="row">有效學分</th><td><strong>70 學分</strong></td>' in output
    assert "修習中課程不計入實得學分" in output
    assert "成績單實得學分：0 學分" not in output


def test_renderer_does_not_guess_zero_when_source_earned_is_missing(monkeypatch):
    snapshot = _snapshot()
    import snapshot_renderer

    original_projection = snapshot_renderer.build_snapshot_projection

    def without_source_earned(value):
        projection = dict(original_projection(value))
        summary = dict(projection["summary"])
        summary.pop("source_earned_credits", None)
        projection["summary"] = summary
        return projection

    monkeypatch.setattr(snapshot_renderer, "build_snapshot_projection", without_source_earned)
    output = render_snapshot(snapshot)

    assert "成績單實得學分：需要補資料 學分" in output
    assert "成績單實得學分：0 學分" not in output


def test_renderer_maps_confirmation_state_and_hides_undefined_required_progress(monkeypatch):
    snapshot = _snapshot()
    import snapshot_renderer

    original_statistics_projection = snapshot_renderer.statistics_projection_from_payload

    def undefined_required(payload):
        statistics = dict(original_statistics_projection(payload))
        statistics["requirement_metrics"] = {
            "items": ({"bucket": "elective", "status": "UNKNOWN", "deficit": "2"},),
        }
        return statistics

    monkeypatch.setattr(snapshot_renderer, "statistics_projection_from_payload", undefined_required)
    output = render_snapshot(snapshot)

    assert "資料確認：已確認" in output
    assert "CONFIRMED" not in output
    assert "請查看要求明細" in output
    assert "0／0 項" not in output


@pytest.mark.parametrize(
    ("state", "label"),
    (("PARSED", "待確認"), ("STALE", "資料已變更"), ("UNCONFIRMED", "待補資料")),
)
def test_renderer_maps_non_confirmed_input_states_without_raw_codes(monkeypatch, state, label):
    snapshot = _snapshot()
    original = DecisionSnapshot.as_dict

    def changed(self):
        payload = dict(original(self))
        payload["input_confirmation"] = {"state": state}
        return payload

    monkeypatch.setattr(DecisionSnapshot, "as_dict", changed)
    output = render_snapshot(snapshot)

    assert f"資料確認：{label}" in output
    assert state not in output


def test_renderer_replaces_missing_evaluated_at_with_student_facing_text(monkeypatch):
    snapshot = _snapshot()
    original = DecisionSnapshot.as_dict

    def unspecified(self):
        payload = dict(original(self))
        payload["evaluated_at"] = "UNSPECIFIED"
        return payload

    monkeypatch.setattr(DecisionSnapshot, "as_dict", unspecified)
    output = render_snapshot(snapshot)

    assert "更新於 本次分析" in output
    assert "UNSPECIFIED" not in output


def test_renderer_hides_internal_course_ids_and_labels_verified_identity(monkeypatch):
    snapshot = _snapshot()
    original = DecisionSnapshot.as_dict
    internal_id = "primary:primary:111:earth:earth_environment:pool:common"

    def internal_course(self):
        payload = dict(original(self))
        requirements = [dict(item) for item in payload["requirements"]]
        core = next(item for item in requirements if item["requirement_id"] == "req-core")
        core["eligible_course_ids"] = (internal_id,)
        core["eligible_course_names"] = ("合法課名",)
        payload["requirements"] = tuple(requirements)
        return payload

    monkeypatch.setattr(DecisionSnapshot, "as_dict", internal_course)
    output = render_snapshot(snapshot)

    assert "合法課名" in output
    assert internal_id not in output
    assert "課程資料：已核對" in output


@pytest.mark.parametrize(
    ("secondary_kind", "visible"),
    (("", False), ("minor", True)),
)
def test_renderer_only_shows_secondary_self_report_for_real_secondary(monkeypatch, secondary_kind, visible):
    snapshot = _snapshot()
    original = DecisionSnapshot.as_dict

    def with_self_report(self):
        payload = dict(original(self))
        decisions = dict(payload["decisions"])
        decisions["application_self_report"] = {"status": "UNKNOWN", "reason": "gate"}
        payload["decisions"] = decisions
        request = dict(payload.get("request") or {})
        if secondary_kind:
            request["secondary_kind"] = secondary_kind
        else:
            request.pop("secondary_kind", None)
        payload["request"] = request
        return payload

    monkeypatch.setattr(DecisionSnapshot, "as_dict", with_self_report)
    output = render_snapshot(snapshot)
    administrative_start = output.index('<section class="snapshot-card"><h2>行政資訊</h2>')
    administrative_end = output.index("</section>", administrative_start)
    administrative = output[administrative_start:administrative_end]

    assert ("申請資料（自行填寫）" in output) is visible
    assert ("gate" in administrative) is visible


def test_renderer_rejects_non_snapshot_objects():
    with pytest.raises(TypeError):
        render_snapshot({})  # type: ignore[arg-type]


def test_requirement_expander_lists_official_choices_unallocated_attempts_and_not_attempted(monkeypatch):
    snapshot = _snapshot()
    original = DecisionSnapshot.as_dict

    def enriched(self):
        payload = dict(original(self))
        requirements = [dict(item) for item in payload["requirements"]]
        core = next(item for item in requirements if item["requirement_id"] == "req-core")
        core.update(
            {
                "eligible_course_ids": ("A-001", "B-001", "C-003"),
                "eligible_course_names": ("核心課程", "普通課程", "尚未修課"),
                "choice_condition": "任選 1 門；依正式課表版本",
            }
        )
        payload["requirements"] = tuple(requirements)
        return payload

    monkeypatch.setattr(DecisionSnapshot, "as_dict", enriched)
    projection = build_snapshot_projection(snapshot)
    core = next(item for item in projection["requirements"] if item["requirement_id"] == "req-core")
    courses = {item["course_id"]: item for item in core["courses"]}

    assert core["choice_condition"] == "任選 1 門；依正式課表版本"
    assert [item["course_id"] for item in core["eligible_courses"]] == ["A-001", "B-001", "C-003"]
    assert courses["A-001"]["is_allocated"] is True
    assert courses["B-001"]["is_allocated"] is False
    assert courses["B-001"]["used_credits"] == "0"
    assert courses["B-001"]["status_label"] == "修習中"
    assert "未配置" in courses["B-001"]["allocation_reason"] or "安全" in courses["B-001"]["allocation_reason"]
    assert courses["C-003"]["status"] == "NOT_ATTEMPTED"
    assert courses["C-003"]["status_label"] == "尚未修課"
    assert courses["C-003"]["used_credits"] == "0"

    output = render_snapshot(snapshot)
    assert "規則指定課程" in output
    assert "任選 1 門；依正式課表版本" in output
    assert "尚未修課" in output
    assert "UNKNOWN" not in output


def test_renderer_recursively_removes_normalized_identity_credentials_and_raw_transcript(monkeypatch):
    snapshot = _snapshot()
    original = DecisionSnapshot.as_dict
    secrets = {
        "student_id": "RAW_STUDENT_ID_RENDERER_9f31",
        "student_number": "RAW_STUDENT_NUMBER_RENDERER_9f31",
        "studentNo": "RAW_STUDENT_NO_RENDERER_9f31",
        "studentId": "RAW_STUDENT_ID_CAMEL_RENDERER_9f31",
        "學號": "原始學號_RENDERER_9f31",
        "student_name": "RAW_STUDENT_NAME_RENDERER_9f31",
        "姓名": "原始姓名_RENDERER_9f31",
        "username": "RAW_USERNAME_RENDERER_9f31",
        "account": "RAW_ACCOUNT_RENDERER_9f31",
        "password": "RAW_PASSWORD_RENDERER_9f31",
        "credential": "RAW_CREDENTIAL_RENDERER_9f31",
        "authorization": "RAW_AUTH_RENDERER_9f31",
        "session": "RAW_SESSION_RENDERER_9f31",
        "cookie": "RAW_COOKIE_RENDERER_9f31",
        "token": "RAW_TOKEN_RENDERER_9f31",
        "HF Token": "RAW_HF_TOKEN_RENDERER_9f31",
        "transcript": "RAW_TRANSCRIPT_RENDERER_9f31",
        "transcriptBytes": "RAW_TRANSCRIPT_BYTES_RENDERER_9f31",
        "pdf": "RAW_PDF_RENDERER_9f31",
        "rawPDF": "RAW_RAW_PDF_RENDERER_9f31",
        "blob": "RAW_BLOB_RENDERER_9f31",
        "bytes": "RAW_BYTES_RENDERER_9f31",
    }

    def hostile(self):
        payload = dict(original(self))
        payload["request"] = {"masked_student_id": "***1234", "nested": dict(secrets)}
        payload["decisions"] = {"safe_decision": {"nested": dict(secrets)}}
        payload["statistics"] = {"safe_statistics": {"nested": dict(secrets)}}
        payload["rule_provenance"] = ({"source_reference": "official:renderer", "nested": dict(secrets)},)
        return payload

    monkeypatch.setattr(DecisionSnapshot, "as_dict", hostile)
    output = render_snapshot(snapshot)
    assert "***1234" in output
    assert all(value not in output for value in secrets.values())


def test_snapshot_theme_bridge_overrides_os_and_legacy_theme_rules():
    output = render_snapshot(_snapshot())
    css = output.split("<style>", 1)[1].split("</style>", 1)[0]

    media_index = css.index("@media (prefers-color-scheme: dark)")
    legacy_indices = [
        css.index(f'html[data-theme="{theme}"] .snapshot-report')
        for theme in ("light", "dark")
    ]
    for theme in ("light", "dark"):
        bridge_index = css.index(f'html[data-utaipei-theme="{theme}"] .snapshot-report')
        assert media_index < bridge_index
        assert max(legacy_indices) < bridge_index

    light_bridge = css.split('html[data-utaipei-theme="light"] .snapshot-report', 1)[1]
    light_bridge = light_bridge.split('html[data-utaipei-theme="dark"] .snapshot-report', 1)[0]
    dark_bridge = css.split('html[data-utaipei-theme="dark"] .snapshot-report', 1)[1]
    for token in (
        "--snapshot-bg: #F8FAFC",
        "--snapshot-card: #FFFFFF",
        "--snapshot-text: #0F172A",
        "--snapshot-muted: #475569",
        "--snapshot-border: #CBD5E1",
        "--snapshot-primary: #1E3A5F",
        "--snapshot-action: #2563EB",
    ):
        assert token in light_bridge
    for token in (
        "--snapshot-bg: #0B1120",
        "--snapshot-card: #111827",
        "--snapshot-text: #F8FAFC",
        "--snapshot-muted: #CBD5E1",
        "--snapshot-border: #334155",
        "--snapshot-primary: #60A5FA",
        "--snapshot-action: #60A5FA",
    ):
        assert token in dark_bridge
