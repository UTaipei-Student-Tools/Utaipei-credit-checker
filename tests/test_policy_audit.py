import unittest

from audit_export import (
    audit_csv_bytes,
    audit_json_bytes,
    build_audit_payload,
    dataframe_csv_bytes,
    flatten_allocation_rows,
)
from policy_audit import (
    COURSE_IDENTITY_CONFLICTED,
    COURSE_IDENTITY_MANUAL_APPROVED,
    COURSE_IDENTITY_UNKNOWN,
    COURSE_IDENTITY_VERIFIED,
    NOT_APPLICABLE,
    SATISFIED,
    SHARED_EVIDENCE_APPROVED,
    SHARED_EVIDENCE_CONFIRMED_ZERO,
    SHARED_EVIDENCE_UNANSWERED,
    UNKNOWN,
    UNSATISFIED,
    assess_cohort_match,
    assess_double_major_eligibility,
    get_admission_cohort_options,
    get_double_structure,
    get_primary_program_options,
    get_primary_requirements,
    get_target_program_options,
)


class PolicyAuditTests(unittest.TestCase):
    def test_cohorts_and_program_matrix(self):
        self.assertEqual(get_admission_cohort_options(), ["111", "112", "113", "114", "115"])
        self.assertIn("數學", get_primary_program_options("114"))
        self.assertIn("數據科學與數學", get_primary_program_options("115"))
        self.assertEqual(get_primary_requirements("115", "物化（應用化學）")["track_required"], 42.0)
        self.assertEqual(get_primary_requirements("114", "資科")["required_courses_credits"], 31.0)

    def test_application_timing_and_status_are_independent_from_cohort(self):
        satisfied = assess_double_major_eligibility(
            admission_cohort="111",
            application_year=2,
            application_semester=1,
            application_status="已核准",
            secondary_credits=40,
            shared_credits=0,
        )
        self.assertEqual(satisfied["status"], SATISFIED)
        too_early = assess_double_major_eligibility(
            admission_cohort="115",
            application_year=1,
            application_semester=2,
            application_status="已核准",
            secondary_credits=40,
            shared_credits=0,
        )
        self.assertEqual(too_early["status"], UNSATISFIED)
        unknown_leave = assess_double_major_eligibility(
            admission_cohort="115",
            application_year=2,
            application_semester=1,
            application_status="申請中",
            secondary_credits=40,
            shared_credits=0,
            leave_history=["休學"],
        )
        self.assertEqual(unknown_leave["status"], UNKNOWN)

    def test_application_year_accepts_actual_roc_years_and_gregorian_years(self):
        roc_satisfied = assess_double_major_eligibility(
            admission_cohort="111",
            application_year="112",
            application_semester=1,
            application_status="已核准",
            secondary_credits=40,
            shared_credits=0,
        )
        self.assertEqual(roc_satisfied["status"], SATISFIED)
        roc_first_year = assess_double_major_eligibility(
            admission_cohort="111",
            application_year="111",
            application_semester=2,
            application_status="已核准",
            secondary_credits=40,
            shared_credits=0,
        )
        self.assertEqual(roc_first_year["status"], UNSATISFIED)
        gregorian_satisfied = assess_double_major_eligibility(
            admission_cohort="115",
            application_year="2029",  # ROC 118
            application_semester=1,
            application_status="已核准",
            secondary_credits=40,
            shared_credits=0,
        )
        self.assertEqual(gregorian_satisfied["status"], SATISFIED)
        fifth_year_second_semester = assess_double_major_eligibility(
            admission_cohort="115",
            application_year="118",
            application_semester=2,
            application_status="已核准",
            secondary_credits=40,
            shared_credits=0,
        )
        self.assertEqual(fifth_year_second_semester["status"], UNSATISFIED)

    def test_double_major_targets_exclude_same_department_tracks(self):
        earth_targets = get_target_program_options("114", "地生（地球環境）")
        self.assertNotIn("地生（生命科學）", earth_targets)
        self.assertTrue(all("地生" not in option for option in earth_targets))
        apc_targets = get_target_program_options("114", "物化（電子物理）")
        self.assertNotIn("物化（應用化學）", apc_targets)

    def test_interrupted_history_is_unknown_and_exported(self):
        result = assess_double_major_eligibility(
            admission_cohort="115",
            application_year="116",
            application_semester=1,
            application_status="已核准",
            secondary_credits=40,
            shared_credits=0,
            interrupted=True,
        )
        self.assertEqual(result["status"], UNKNOWN)
        self.assertTrue(result["interrupted"])

    def test_shared_evidence_distinguishes_unanswered_zero_and_approved(self):
        kwargs = {
            "admission_cohort": "111",
            "application_year": "112",
            "application_semester": 1,
            "application_status": "已核准",
            "secondary_credits": 40,
        }
        unanswered = assess_double_major_eligibility(**kwargs)
        self.assertEqual(unanswered["shared_credit_state"], SHARED_EVIDENCE_UNANSWERED)
        self.assertEqual(unanswered["status"], UNKNOWN)
        confirmed_zero = assess_double_major_eligibility(
            **kwargs, shared_evidence_state="confirmed_zero", shared_credits=0, shared_approved=True
        )
        self.assertEqual(confirmed_zero["shared_credit_state"], SHARED_EVIDENCE_CONFIRMED_ZERO)
        self.assertEqual(confirmed_zero["status"], SATISFIED)
        approved = assess_double_major_eligibility(
            **kwargs, shared_evidence_state="approved", shared_credits=3, shared_approved=True
        )
        self.assertEqual(approved["shared_credit_state"], SHARED_EVIDENCE_APPROVED)
        self.assertEqual(approved["status"], UNKNOWN)
        self.assertEqual(approved["shared_reuse_allowance"], 0)
        self.assertTrue(approved["legacy_unbound"])
        bound = assess_double_major_eligibility(
            **kwargs,
            shared_evidence_state="approved",
            shared_credits=3,
            shared_approved=True,
            equivalency_bound=True,
        )
        self.assertEqual(bound["status"], SATISFIED)
        self.assertEqual(bound["shared_reuse_allowance"], 3)

    def test_cohort_mismatch_requires_explicit_audit_confirmation(self):
        pending = assess_cohort_match("114", "113")
        self.assertEqual(pending["status"], UNKNOWN)
        confirmed = assess_cohort_match("114", "113", confirmed=True)
        self.assertEqual(confirmed["status"], SATISFIED)

    def test_parser_identity_gap_blocks_allocated_earth_course(self):
        from credit_engine import evaluate_graduation
        from pdf_parser import build_course_dict

        course = build_course_dict("地質學", "必", "3", "80", "", "", "114")
        report = evaluate_graduation(
            [course],
            {
                "domain": "地球環境",
                "program": "單主修",
                "handbook_year": "114",
                "parser_diagnostics": {
                    "complete": True,
                    "fatal": False,
                    "course_code_missing": 4,
                    "offering_department_missing": 4,
                    "identity_complete": False,
                },
            },
        )
        self.assertEqual(report["summary"]["graduation_status"], UNKNOWN)
        self.assertEqual(report["identity_gate"]["status"], COURSE_IDENTITY_UNKNOWN)
        fatal = evaluate_graduation(
            [],
            {
                "domain": "地球環境",
                "program": "單主修",
                "handbook_year": "114",
                "parser_diagnostics": {"complete": False, "fatal": True, "fatal_warnings": ["bad PDF"]},
            },
        )
        self.assertEqual(fatal["summary"]["graduation_status"], UNKNOWN)

    def test_course_identity_paths_and_fallback_conserve_credits(self):
        from credit_engine import evaluate_graduation
        from equivalency_audit import source_attempt_id
        from handbook_rules import get_apc_target_requirements
        from pdf_parser import build_course_dict

        def earth_course(year, code="", department=""):
            course = build_course_dict("地質學", "必", "3", "80", "", "", year)
            course["course_code"] = code
            course["offering_department"] = department
            return course

        correct = evaluate_graduation(
            [earth_course("114", "GE-101", "地生系")],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "114"},
        )
        self.assertEqual(correct["major"]["domain_compulsory_courses"][0]["identity_status"], COURSE_IDENTITY_VERIFIED)
        self.assertTrue(correct["graduation_gates"]["course_identity"])
        self.assertTrue(correct["audit"]["credit_conservation"])

        wrong = earth_course("114", "CS-101", "資訊科學系")
        valid = earth_course("115", "GE-102", "地生系")
        fallback = evaluate_graduation(
            [wrong, valid],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "114"},
        )
        self.assertEqual(len(fallback["major"]["domain_compulsory_courses"]), 1)
        self.assertEqual(fallback["major"]["domain_compulsory_courses"][0]["course_code"], "GE-102")
        self.assertTrue(any(course.get("course_code") == "CS-101" for course in fallback["free"]["courses"]))
        self.assertEqual(fallback["identity_issues"][0]["identity_status"], COURSE_IDENTITY_CONFLICTED)
        self.assertTrue(fallback["graduation_gates"]["course_identity"])
        self.assertTrue(fallback["audit"]["credit_conservation"])

        missing = evaluate_graduation(
            [earth_course("114")],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "114"},
        )
        self.assertEqual(missing["major"]["domain_compulsory_courses"][0]["identity_status"], COURSE_IDENTITY_UNKNOWN)
        self.assertEqual(missing["identity_gate"]["status"], COURSE_IDENTITY_UNKNOWN)
        self.assertEqual(missing["summary"]["graduation_status"], UNKNOWN)
        self.assertFalse(missing["graduation_gates"]["course_identity"])
        self.assertTrue(missing["audit"]["credit_conservation"])

        target_plan = get_apc_target_requirements("114", "化學組", "雙主修")
        target_row = next(row for row in target_plan["requirements"] if row["name"] == "普通物理學(一)")
        manual_course = build_course_dict("普通物理學(一)", "必", "3", "80", "", "", "114")
        manual_decision = {
            "decision_id": "decision:identity-001",
            "source_attempt_id": source_attempt_id(manual_course),
            "source_course_name": manual_course["name"],
            "target_requirement_id": target_row["id"],
            "target_requirement_name": target_row["name"],
            "cohort": "114",
            "target_program": "物化",
            "target_track": "化學組",
            "program_type": "雙主修",
            "state": "approved",
            "decision": "approved",
            "authority": "物化系課程委員會",
            "evidence_reference": "核准單-identity-001",
        }
        manual = evaluate_graduation(
            [manual_course],
            {
                "domain": "地球環境",
                "program": "雙主修",
                "target_dept": "物化系化學組",
                "handbook_year": "114",
                "application_year": "115",
                "application_semester": 1,
                "application_status": "已核准",
                "target_requirements": target_plan,
                "equivalency_decisions": [manual_decision],
            },
        )
        self.assertEqual(manual["target"]["basic_core_courses"][0]["identity_status"], COURSE_IDENTITY_MANUAL_APPROVED)
        self.assertEqual(manual["target"]["basic_core_courses"][0]["identity_authority"], "物化系課程委員會")
        self.assertEqual(manual["target"]["basic_core_courses"][0]["identity_evidence_reference"], "核准單-identity-001")
        self.assertEqual(manual["identity_gate"]["status"], COURSE_IDENTITY_MANUAL_APPROVED)
        self.assertTrue(manual["graduation_gates"]["course_identity"])
        self.assertTrue(manual["audit"]["credit_conservation"])

    def test_allocated_identity_gate_ignores_rejected_conflict(self):
        from credit_engine import evaluate_graduation
        from pdf_parser import build_course_dict

        wrong = build_course_dict("地質學", "必", "3", "80", "", "", "114")
        wrong.update({"course_code": "WRONG-TERM", "offering_department": "資訊科學系"})
        valid = build_course_dict("地質學", "必", "3", "90", "", "", "115")
        valid.update({"course_code": "EARTH-TERM", "offering_department": "地生系"})
        report = evaluate_graduation(
            [wrong, valid],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "114"},
        )

        self.assertEqual(report["identity_gate"]["status"], COURSE_IDENTITY_VERIFIED)
        self.assertEqual(report["identity_gate"]["rejected_conflicted_count"], 1)
        self.assertTrue(report["graduation_gates"]["course_identity"])
        self.assertTrue(report["audit"]["credit_conservation"])

    def test_allocated_unknown_identity_is_one_issue_and_exported_once(self):
        from credit_engine import evaluate_graduation
        from pdf_parser import build_course_dict

        course = build_course_dict("地質學", "必", "3", "80", "", "", "114")
        report = evaluate_graduation(
            [course],
            {"domain": "地球環境", "program": "單主修", "handbook_year": "114"},
        )
        unknown = [item for item in report["identity_issues"] if item.get("identity_status") == COURSE_IDENTITY_UNKNOWN]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(report["identity_gate"]["unknown_count"], 1)
        self.assertEqual(report["identity_gate"]["status"], COURSE_IDENTITY_UNKNOWN)
        self.assertIn("需系所確認", unknown[0]["identity_reason"])

        payload = build_audit_payload({"report": report})
        exported_unknown = [
            item for item in payload["identity_issues"] if item.get("identity_status") == COURSE_IDENTITY_UNKNOWN
        ]
        self.assertEqual(len(exported_unknown), 1)
        self.assertEqual(payload["identity_gate"]["status"], COURSE_IDENTITY_UNKNOWN)
        self.assertEqual(payload["identity_gate"]["reasons"], report["identity_gate"]["reasons"])

    def test_same_term_duplicate_collapses_but_different_term_survives(self):
        from credit_engine import _canonicalize_courses
        from pdf_parser import build_course_dict

        same_term_low = build_course_dict("地質學", "必", "3", "70", "", "", "114")
        same_term_high = build_course_dict("地質學", "必", "3", "90", "", "", "114")
        next_term = build_course_dict("地質學", "必", "3", "80", "", "", "115")
        selected, meta = _canonicalize_courses([next_term, same_term_low, same_term_high])
        self.assertEqual(meta["deduplicated_count"], 1)
        self.assertEqual(len(selected), 2)
        self.assertEqual({item["academic_year"] for item in selected}, {"114", "115"})
        self.assertEqual(len({item["attempt_id"] for item in selected}), 2)

    def test_approved_shared_reuse_is_separate_from_raw_conservation(self):
        from credit_engine import _build_shared_reuse_allocations, evaluate_graduation
        from pdf_parser import build_course_dict

        course = build_course_dict("地質學", "必", "3", "80", "", "", "114")
        report = evaluate_graduation(
            [course],
            {
                "domain": "地球環境",
                "program": "雙主修",
                "target_dept": "物化系化學組",
                "handbook_year": "114",
                "application_year": "115",
                "application_semester": 1,
                "application_status": "已核准",
                "shared_evidence_state": "approved",
                "shared_credits": 2,
                "shared_approved": True,
            },
        )
        self.assertTrue(report["audit"]["credit_conservation"])
        self.assertEqual(report["shared_reuse"]["completed"], 0)
        self.assertEqual(report["target"]["total_completed"], 0)
        self.assertEqual(report["target"]["effective_total_completed"], 0)
        shared_reuse = _build_shared_reuse_allocations(report, 2)
        self.assertEqual(len(shared_reuse["rows"]), 0)
        self.assertEqual(shared_reuse["approval_scope"], "legacy_unbound")
        self.assertEqual(shared_reuse["allocation_type"], "not_counted")
        self.assertEqual(shared_reuse["course_identity_status"], "not_bound")
        self.assertIn("不計入有效進度", shared_reuse["official_course_identity_note"])

        payload = build_audit_payload({"report": report, "shared_reuse": shared_reuse})
        self.assertEqual(payload["shared_reuse"]["approval_scope"], "legacy_unbound")
        self.assertIn("不計入有效進度", payload["shared_reuse"]["official_course_identity_note"])
        csv_text = audit_csv_bytes({"report": report, "shared_reuse": shared_reuse}).decode("utf-8-sig")
        self.assertIn("shared_reuse_approval_scope", csv_text)
        self.assertIn("legacy_unbound", csv_text)
        self.assertIn("不計入有效進度", csv_text)

    def test_double_structures_and_citations(self):
        self.assertEqual(get_double_structure("111", "地生")["base_required"], 24.0)
        self.assertEqual(get_double_structure("115", "數學")["other_required"], 26.0)
        self.assertEqual(get_double_structure("111", "數學")["status"], SATISFIED)
        citation = get_double_structure("115", "資科")["citations"][0]
        self.assertEqual(citation["file"], "3-理學院 (115).pdf")
        self.assertIn("p.127", citation["pages"])

    def test_registry_metadata_preserves_canonical_track_slugs(self):
        chemistry = get_double_structure("114", "物化", "chemistry")
        self.assertEqual(chemistry["track_slug"], "chemistry")
        self.assertEqual(chemistry["curriculum_id"], "target:double_major:114:apc:chemistry")

        life_science = get_primary_requirements("114", "地生", "life_science")
        self.assertEqual(life_science["curriculum_id"], "primary:114:earth:life_science")
        self.assertEqual(life_science["curriculum_kind"], "primary")

    def test_single_major_is_not_applicable(self):
        result = assess_double_major_eligibility(program_type="單主修")
        self.assertEqual(result["status"], NOT_APPLICABLE)

    def test_audit_exports_harden_formula_cells(self):
        audit = {
            "cohort": "115",
            "primary_program": "=do-not-run",
            "status": UNKNOWN,
            "requirements": {"total": 128},
            "warnings": ["ordinary warning"],
            "citations": [{"file": "3-理學院 (115).pdf", "pages": "PDF p.127"}],
        }
        csv_text = audit_csv_bytes(audit).decode("utf-8-sig")
        self.assertIn("'=do-not-run", csv_text)
        self.assertIn("cohort", csv_text)
        self.assertIn(b'"cohort"', audit_json_bytes(audit))

    def test_audit_export_flattens_allocations_and_application_fields(self):
        report = {
            "handbook_year": "114",
            "program_type": "雙主修",
            "application": {"interrupted": True},
            "summary": {"graduation_status": UNKNOWN},
            "graduation_gates": {"total": False, "course_identity": False},
            "identity_gate": {
                "status": COURSE_IDENTITY_UNKNOWN,
                "reasons": ["待確認身分"],
                "unknown_count": 1,
            },
            "identity_issues": [{"identity_status": COURSE_IDENTITY_UNKNOWN, "identity_reason": "待確認身分"}],
            "manual_gates": {"cs": {"status": UNKNOWN}},
            "common": {
                "compulsory_courses": [
                    {
                        "name": "=危險課",
                        "completed_credit": 2,
                        "total_credit": 2,
                        "is_completed": True,
                        "identity_status": COURSE_IDENTITY_MANUAL_APPROVED,
                        "identity_reason": "系所核准替代",
                        "identity_authority": "系所課程委員會",
                        "identity_evidence_reference": "核准單-002",
                    }
                ],
                "categories": {"藝術與美感": {"courses": []}},
                "category_overflow": {"藝術與美感": []},
                "common_elective_courses": [],
            },
            "major": {},
            "target": {},
            "pe": {},
            "free": {},
            "requirements": {"total": 128},
            "policy_warnings": [],
            "document_warnings": [],
            "citations": [],
        }
        rows = flatten_allocation_rows(report)
        self.assertEqual(rows[0]["bucket"], "common_compulsory")
        self.assertEqual(rows[0]["allocated_completed_credits"], 2.0)
        self.assertEqual(rows[0]["identity_status"], COURSE_IDENTITY_MANUAL_APPROVED)
        self.assertEqual(rows[0]["identity_reason"], "系所核准替代")
        self.assertEqual(rows[0]["authority"], "系所課程委員會")
        self.assertEqual(rows[0]["evidence_reference"], "核准單-002")
        payload = build_audit_payload(
            {
                "report": report,
                "eligibility": {
                    "status": UNKNOWN,
                    "application_year": "114",
                    "application_semester": "1",
                    "application_status": "申請中",
                    "interrupted": True,
                },
            }
        )
        self.assertEqual(payload["application"]["application_year"], "114")
        self.assertTrue(payload["application"]["interrupted"])
        self.assertEqual(payload["gate_results"]["total"], False)
        self.assertEqual(payload["identity_gate"]["status"], COURSE_IDENTITY_UNKNOWN)
        self.assertEqual(payload["identity_issues"][0]["identity_reason"], "待確認身分")
        self.assertEqual(payload["allocation_rows"][0]["course_name"], "=危險課")
        csv_text = audit_csv_bytes({"report": report, "allocation_rows": rows, "primary_program": "資科"}).decode("utf-8-sig")
        self.assertIn("allocation_rows", csv_text)
        self.assertIn("identity_gate_status", csv_text)
        self.assertIn("identity_reason", csv_text)
        self.assertIn("系所課程委員會", csv_text)
        self.assertIn("核准單-002", csv_text)

    def test_dataframe_csv_export_hardens_formula_like_values(self):
        import pandas as pd

        csv_text = dataframe_csv_bytes(pd.DataFrame([{"課程": "=SUM(A1)", "備註": "@mention"}])).decode("utf-8")
        self.assertIn("'=SUM(A1)", csv_text)
        self.assertIn("'@mention", csv_text)

    def test_parser_department_detection_contract(self):
        from pdf_parser import detect_department_track

        self.assertEqual(detect_department_track("主修系所：資訊科學系"), {"department": "資科", "track": None, "matched_text": "資訊科學系"})
        self.assertEqual(detect_department_track("主修系所：應用化學組")["department"], "物化")
        self.assertEqual(detect_department_track("主修系所：數據科學與數學系")["department"], "數學")

    def test_non_earth_plan_is_threshold_only_and_unknown(self):
        from credit_engine import evaluate_graduation

        report = evaluate_graduation(
            [],
            {"admission_cohort": "115", "primary_program": "資科", "program_type": "單主修"},
        )
        self.assertFalse(report["detailed"])
        self.assertEqual(report["summary"]["graduation_status"], UNKNOWN)
        self.assertEqual(report["target"]["compulsory_courses"], [])
        self.assertEqual(report["primary_plan"]["required_courses_credits"], 31.0)

    def test_repeated_records_are_collapsed_and_credit_is_conserved(self):
        from credit_engine import evaluate_graduation
        from pdf_parser import build_course_dict

        completed_low = build_course_dict("地質學", "必", "3", "80", "", "", "114")
        completed_high = build_course_dict("地質學", "必", "3", "90", "", "", "114")
        first = evaluate_graduation([completed_low, completed_high], {"domain": "地球環境", "program": "單主修", "handbook_year": "114"})
        second = evaluate_graduation([completed_high, completed_low], {"domain": "地球環境", "program": "單主修", "handbook_year": "114"})
        self.assertEqual(first["audit"]["deduplicated_count"], 1)
        self.assertTrue(first["audit"]["credit_conservation"])
        self.assertEqual(first["summary"], second["summary"])
        self.assertEqual(first["major"]["domain_compulsory_courses"][0]["sem1_score"], "90")

    def test_empty_earth_report_does_not_pass_subbucket_gates(self):
        from credit_engine import evaluate_graduation

        report = evaluate_graduation([], {"domain": "地球環境", "program": "單主修", "handbook_year": "114"})
        self.assertFalse(report["summary"]["graduation_ready"])
        self.assertEqual(report["summary"]["graduation_status"], "NOT_SATISFIED")
        self.assertFalse(report["graduation_gates"]["ge_categories"])
        self.assertFalse(report["graduation_gates"]["ge_common_elective"])

    def test_exact_cap_slices_overflow_without_losing_credits(self):
        from credit_engine import _cap_course_bucket
        from pdf_parser import build_course_dict

        courses = [
            build_course_dict("甲課", "選", "3", "80", "", "", "114"),
            build_course_dict("乙課", "選", "3", "80", "", "", "114"),
        ]
        accepted, overflow, completed, in_progress = _cap_course_bucket(courses, 4, "測試")
        self.assertEqual((completed, in_progress), (4.0, 0.0))
        self.assertEqual(sum(item["completed_credit"] for item in accepted), 4.0)
        self.assertEqual(sum(item["completed_credit"] for item in overflow), 2.0)
        self.assertEqual(sum(item["completed_credit"] for item in accepted + overflow), 6.0)


if __name__ == "__main__":
    unittest.main()
