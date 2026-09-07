import unittest
from copy import deepcopy

from equivalency_audit import (
    APPLY_PROVENANCE_REQUIRED,
    APPLY_SCOPE_MISMATCH,
    APPROVED,
    EQUIVALENCY_UNKNOWN,
    EXCLUSIVE_APPLY_UNSUPPORTED,
    LAB_NOT_SPLIT,
    LEGACY_UNBOUND,
    SHARED_LIMIT_EXCEEDED,
    SOURCE_ALREADY_BOUND,
    SOURCE_NOT_FOUND,
    TARGET_CONTEXT_MISMATCH,
    TARGET_OVERFILLED,
    apply_equivalency_audit_to_report,
    audit_equivalency_decisions,
    detect_equivalency_candidates,
    source_attempt_id,
)
from handbook_rules import get_apc_target_requirements


def _course(name, credits=3.0, *, attempt_id=None, academic_year="114", completed=None, in_progress=False):
    earned = credits if completed is None else completed
    return {
        "name": name,
        "raw_name": name,
        "attempt_id": attempt_id or f"attempt:{name}:{academic_year}",
        "academic_year": academic_year,
        "semester": "1",
        "total_credit": float(credits),
        "completed_credit": float(earned),
        "is_completed": float(earned) >= float(credits) and not in_progress,
        "is_in_progress": bool(in_progress),
    }


def _context(cohort="115", track="化學組", program_type="雙主修"):
    return {
        "admission_cohort": cohort,
        "target_program": "物化",
        "target_track": track,
        "program_type": program_type,
    }


def _decision(course, target, *, state=APPROVED, credits=None, **overrides):
    result = {
        "decision_id": f"decision:{source_attempt_id(course)}:{target['id']}",
        "source_attempt_id": source_attempt_id(course),
        "source_course_name": course["name"],
        "target_requirement_id": target["id"],
        "target_requirement_name": target["name"],
        "cohort": "115",
        "target_program": "物化",
        "target_track": "化學組",
        "program_type": "雙主修",
        "state": state,
        "decision": state,
        "authority": "物化系課程委員會核章",
        "evidence_reference": "115手冊 p.25／核准單-001",
    }
    if credits is not None:
        result["approved_credits"] = credits
    result.update(overrides)
    return result


class EquivalencyAuditTests(unittest.TestCase):
    def setUp(self):
        self.plan115 = get_apc_target_requirements("115", "化學組", "雙主修")
        self.calculus1 = next(row for row in self.plan115["requirements"] if row["name"] == "微積分(一)")
        self.calculus2 = next(row for row in self.plan115["requirements"] if row["name"] == "微積分(二)")
        self.physics_lab1 = next(row for row in self.plan115["requirements"] if row["name"] == "普通化學實驗(一)")
        self.other_required = next(row for row in self.plan115["requirements"] if row["kind"] == "quota")

    def test_v2_attempt_id_separates_same_term_code_and_department(self):
        first = _course("同名課程", academic_year="114")
        second = _course("同名課程", academic_year="114")
        first.pop("attempt_id", None)
        second.pop("attempt_id", None)
        first.update({"course_code": "A-101", "offering_department": "地生系"})
        second.update({"course_code": "B-101", "offering_department": "資科系"})

        first_id = source_attempt_id(first)
        second_id = source_attempt_id(second)

        self.assertTrue(first_id.startswith("attempt:v2:"))
        self.assertNotEqual(first_id, second_id)

    def test_binding_v2_source_cannot_attach_to_same_term_different_identity(self):
        plan114 = get_apc_target_requirements("114", "化學組", "雙主修")
        target = next(row for row in plan114["requirements"] if row["name"] == "普通物理學(一)")
        source_a = _course("同名來源", academic_year="114")
        source_b = _course("同名來源", academic_year="114")
        source_a.pop("attempt_id", None)
        source_b.pop("attempt_id", None)
        source_a.update({"course_code": "A-101", "offering_department": "地生系"})
        source_b.update({"course_code": "B-101", "offering_department": "資科系"})
        decision = _decision(source_a, target, cohort="114")

        audit = audit_equivalency_decisions(
            [source_a, source_b],
            plan114,
            [decision],
            context=_context(cohort="114"),
            include_candidates=False,
        )

        self.assertEqual(len(audit["approved_mappings"]), 1)
        self.assertEqual(audit["approved_mappings"][0]["source_attempt_id"], source_attempt_id(source_a))
        self.assertNotEqual(source_attempt_id(source_a), source_attempt_id(source_b))

    def test_literal_legacy_attempt_id_requires_reapproval(self):
        plan114 = get_apc_target_requirements("114", "化學組", "雙主修")
        target = next(row for row in plan114["requirements"] if row["name"] == "普通物理學(一)")
        source = _course("舊版來源", academic_year="114")
        source.pop("attempt_id", None)
        source.update({"course_code": "OLD-101", "offering_department": "地生系"})
        decision = _decision(
            source,
            target,
            cohort="114",
            source_attempt_id="attempt:舊版來源|3.0|114||3|",
            decision_id="decision:legacy-v1",
        )

        audit = audit_equivalency_decisions(
            [source],
            plan114,
            [decision],
            context=_context(cohort="114"),
            include_candidates=False,
        )

        self.assertEqual(audit["approved_mappings"], [])
        self.assertIn(SOURCE_NOT_FOUND, audit["decisions"][0]["validation_codes"])

    def test_legacy_aggregate_is_warning_only_and_never_effective_credit(self):
        course = _course("舊版來源課", attempt_id="src-legacy")
        audit = audit_equivalency_decisions(
            [course],
            self.plan115,
            [],
            context={**_context(), "shared_course_credits": 3},
            include_candidates=False,
        )
        self.assertEqual(audit["status"], EQUIVALENCY_UNKNOWN)
        self.assertTrue(audit["legacy_unbound"])
        self.assertIn(LEGACY_UNBOUND, audit["validation_codes"])
        self.assertEqual(audit["approved_shared_reuse_credits"], 0.0)

        report = {
            "target": {"total_completed": 0.0},
            "summary": {"total_completed": 0.0},
        }
        applied = apply_equivalency_audit_to_report(report, audit)
        self.assertEqual(applied["target"]["effective_total_completed"], 0.0)
        self.assertEqual(applied["shared_reuse"]["completed"], 0.0)

    def test_only_evidence_backed_approved_binding_counts(self):
        course = _course("微積分", attempt_id="src-calculus")
        audit = audit_equivalency_decisions(
            [course],
            self.plan115,
            [_decision(course, self.calculus1)],
            context=_context(),
            include_candidates=False,
        )
        self.assertEqual(audit["status"], "SATISFIED")
        self.assertEqual(len(audit["approved_mappings"]), 1)
        mapping = audit["approved_mappings"][0]
        self.assertTrue(mapping["counts"])
        self.assertEqual(mapping["approved_credits"], 3.0)
        self.assertEqual(mapping["allocation_type"], "exclusive_reclassification")

        no_evidence = audit_equivalency_decisions(
            [course],
            self.plan115,
            [_decision(course, self.calculus1, authority="", evidence_reference="")],
            context=_context(),
            include_candidates=False,
        )
        self.assertEqual(no_evidence["approved_mappings"], [])
        self.assertTrue(no_evidence["decisions"][0]["manual_review"])

    def test_115_plain_calculus_has_two_candidates_but_never_auto_counts(self):
        course = _course("微積分", attempt_id="src-plain-calculus")
        candidates = detect_equivalency_candidates([course], self.plan115)
        self.assertEqual({item["target_requirement_name"] for item in candidates}, {"微積分(一)", "微積分(二)"})
        self.assertTrue(all(item["state"] != APPROVED and item["approved_credits"] == 0 for item in candidates))

        audit = audit_equivalency_decisions([course], self.plan115, [], context=_context())
        self.assertEqual(audit["approved_mappings"], [])
        self.assertEqual(audit["status"], EQUIVALENCY_UNKNOWN)

    def test_111_to_114_chemistry_does_not_auto_add_calculus(self):
        plan114 = get_apc_target_requirements("114", "化學組", "雙主修")
        course = _course("微積分", attempt_id="src-old-calculus")
        self.assertEqual(detect_equivalency_candidates([course], plan114), [])
        self.assertFalse(any(row["name"].startswith("微積分") for row in plan114["requirements"]))

    def test_combined_lecture_cannot_fill_lab(self):
        course = _course("普通化學(含實驗)", attempt_id="src-combined")
        audit = audit_equivalency_decisions(
            [course],
            self.plan115,
            [_decision(course, self.physics_lab1)],
            context=_context(),
            include_candidates=False,
        )
        self.assertEqual(audit["approved_mappings"], [])
        self.assertIn(LAB_NOT_SPLIT, audit["decisions"][0]["validation_codes"])

    def test_scope_and_target_capacity_are_validated(self):
        first = _course("微積分", attempt_id="src-first")
        second = _course("跨系數學", attempt_id="src-second")
        wrong_scope = _decision(first, self.calculus1, program_type="輔系")
        full = audit_equivalency_decisions(
            [first, second],
            self.plan115,
            [
                _decision(first, self.calculus1),
                # Reusing the same exact source attempt must fail even when
                # the target row is also already full.
                _decision(first, self.calculus1),
            ],
            context=_context(),
            include_candidates=False,
        )
        self.assertEqual(len(full["approved_mappings"]), 1)
        self.assertIn(SOURCE_ALREADY_BOUND, full["decisions"][1]["validation_codes"])
        self.assertIn(TARGET_OVERFILLED, full["decisions"][1]["validation_codes"])

        mismatch = audit_equivalency_decisions(
            [first], self.plan115, [wrong_scope], context=_context(), include_candidates=False
        )
        self.assertEqual(mismatch["approved_mappings"], [])
        self.assertIn(TARGET_CONTEXT_MISMATCH, mismatch["decisions"][0]["validation_codes"])

    def test_primary_source_uses_shared_cap_and_common_course_is_not_primary(self):
        primary_a = _course("主修必修甲", attempt_id="src-primary-a", credits=3)
        primary_b = _course("主修必修乙", attempt_id="src-primary-b", credits=4)
        report = {
            "major": {
                "dept_compulsory_courses": [primary_a, primary_b],
                "domain_compulsory_courses": [],
                "domain_elective_courses": [],
                "other_elective_courses": [],
            },
            "common": {"compulsory_courses": [], "common_elective_courses": [], "categories": {}},
            "free": {"courses": []},
            "target": {},
        }
        audit = audit_equivalency_decisions(
            [primary_a, primary_b],
            self.plan115,
            [
                _decision(primary_a, self.calculus1),
                _decision(primary_b, self.other_required, credits=4),
            ],
            context=_context(),
            report=report,
            include_candidates=False,
        )
        self.assertEqual(len(audit["approved_mappings"]), 1)
        self.assertEqual(audit["approved_shared_reuse_credits"], 3.0)
        self.assertIn(SHARED_LIMIT_EXCEEDED, audit["decisions"][1]["validation_codes"])

        common = _course("英文", attempt_id="src-common", credits=3)
        common_report = {
            "common": {"compulsory_courses": [common], "common_elective_courses": [], "categories": {}},
            "major": {},
            "free": {"courses": []},
            "target": {},
        }
        common_audit = audit_equivalency_decisions(
            [common], self.plan115, [_decision(common, self.calculus1)], context=_context(), report=common_report, include_candidates=False
        )
        # A non-primary source may be moved exclusively when the report can
        # identify exactly one source bucket; it is not eligible for shadow
        # reuse, but it remains a valid auditable reclassification.
        self.assertEqual(common_audit["approved_mappings"][0]["allocation_type"], "exclusive_reclassification")

    def test_apply_does_not_trust_hand_built_aggregate_or_unvalidated_rows(self):
        report = {"target": {"total_completed": 0.0}, "summary": {"total_completed": 0.0}}
        audit = {
            "approved_shared_reuse_credits": 6.0,
            "approved_mappings": [
                {
                    "state": APPROVED,
                    "decision": APPROVED,
                    "source_attempt_id": "src",
                    "target_requirement_id": self.calculus1["id"],
                    "approved_credits": 3,
                    "authority": "",
                    "evidence_reference": "",
                    "allocation_type": "shadow_reuse",
                }
            ],
            "manual_gate": {"status": EQUIVALENCY_UNKNOWN},
            "warnings": [],
        }
        applied = apply_equivalency_audit_to_report(report, audit)
        self.assertEqual(applied["target"]["effective_total_completed"], 0.0)
        self.assertEqual(applied["shared_reuse"]["completed"], 0.0)

    def test_exclusive_reclassification_is_rejected_before_stale_gate_mutation(self):
        source = _course("微積分", attempt_id="src-exclusive")
        report = {
            "handbook_year": "115",
            "program_type": "雙主修",
            "target_dept": "物化系化學組",
            "target_requirements": self.plan115,
            "target": {
                "total_completed": 0.0,
                "total_ip": 0.0,
                "basic_core_completed": 0.0,
                "basic_core_courses": [],
                "compulsory_completed": 0.0,
                "compulsory_courses": [],
                "elective_completed": 0.0,
                "elective_courses": [],
            },
            "major": {},
            "common": {},
            "free": {"courses": [source], "completed": 3.0, "ip": 0.0},
            "summary": {"total_completed": 3.0, "free_completed": 3.0},
        }
        audit = audit_equivalency_decisions(
            [source],
            self.plan115,
            [_decision(source, self.calculus1)],
            context=_context(),
            report=report,
            include_candidates=False,
        )
        self.assertEqual(audit["approved_mappings"][0]["allocation_type"], "exclusive_reclassification")
        applied = apply_equivalency_audit_to_report(report, audit)
        self.assertEqual(applied["target"]["effective_total_completed"], 0.0)
        self.assertEqual(applied["target"]["equivalency_courses"], [])
        self.assertEqual(len(applied["free"]["courses"]), 1)
        self.assertTrue(any(EXCLUSIVE_APPLY_UNSUPPORTED in warning for warning in applied["policy_warnings"]))

    def test_existing_generic_quota_capacity_blocks_overfill(self):
        source = _course("主修必修", attempt_id="src-quota", credits=3.0)
        report = {
            "handbook_year": "115",
            "program_type": "雙主修",
            "target_dept": "物化系化學組",
            "target_requirements": self.plan115,
            "target": {
                "total_completed": 19.0,
                "total_ip": 0.0,
                "basic_core_completed": 0.0,
                "basic_core_courses": [],
                "compulsory_completed": 19.0,
                "compulsory_ip": 0.0,
                "compulsory_courses": [],
                "elective_completed": 0.0,
                "elective_courses": [],
            },
            "major": {"dept_compulsory_courses": [source]},
            "common": {},
            "free": {"courses": []},
            "summary": {"total_completed": 19.0},
        }
        audit = audit_equivalency_decisions(
            [source],
            self.plan115,
            [_decision(source, self.other_required, credits=3.0)],
            context=_context(),
            report=report,
            include_candidates=False,
        )
        self.assertEqual(audit["approved_mappings"], [])
        self.assertIn(TARGET_OVERFILLED, audit["decisions"][0]["validation_codes"])
        applied = apply_equivalency_audit_to_report(report, audit)
        self.assertEqual(applied["target"]["compulsory_completed"], 19.0)
        self.assertEqual(applied["target"]["effective_total_completed"], 19.0)

    def test_apply_rejects_forged_mapping_and_scope_or_capacity_changes(self):
        source = _course("地質學", attempt_id="src-forged")
        report = {
            "handbook_year": "115",
            "program_type": "雙主修",
            "target_dept": "物化系化學組",
            "target_requirements": self.plan115,
            "target": {
                "total_completed": 0.0,
                "total_ip": 0.0,
                "basic_core_completed": 0.0,
                "basic_core_courses": [],
                "compulsory_completed": 0.0,
                "compulsory_courses": [],
                "elective_completed": 0.0,
                "elective_courses": [],
                "equivalency_courses": [],
            },
            "major": {"dept_compulsory_courses": [source]},
            "common": {},
            "free": {"courses": []},
            "summary": {},
        }
        valid = audit_equivalency_decisions(
            [source],
            self.plan115,
            [_decision(source, self.calculus1)],
            context=_context(),
            report=report,
            include_candidates=False,
        )
        forged = deepcopy(valid)
        forged["approved_mappings"][0]["source_attempt_id"] = "ghost-source"
        ghost = apply_equivalency_audit_to_report(report, forged)
        self.assertEqual(ghost["target"]["effective_total_completed"], 0.0)
        self.assertTrue(any(APPLY_PROVENANCE_REQUIRED in warning for warning in ghost["policy_warnings"]))

        wrong_scope_report = deepcopy(report)
        wrong_scope_report["handbook_year"] = "114"
        wrong_scope = apply_equivalency_audit_to_report(wrong_scope_report, valid)
        self.assertEqual(wrong_scope["target"]["effective_total_completed"], 0.0)
        self.assertTrue(any(APPLY_SCOPE_MISMATCH in warning for warning in wrong_scope["policy_warnings"]))

        over_capacity_report = deepcopy(report)
        over_capacity_report["target"]["total_completed"] = 3.0
        over_capacity_report["target"]["basic_core_courses"] = [
            {"target_requirement_id": self.calculus1["id"], "completed_credit": 3.0, "total_credit": 3.0}
        ]
        over_capacity = apply_equivalency_audit_to_report(over_capacity_report, valid)
        self.assertEqual(over_capacity["target"]["effective_total_completed"], 3.0)
        self.assertEqual(over_capacity["target"]["equivalency_courses"], [])
        self.assertTrue(any(TARGET_OVERFILLED in warning for warning in over_capacity["policy_warnings"]))

        forged_complete = {
            "approved_mappings": [
                {
                    "decision_id": "forged",
                    "state": APPROVED,
                    "decision": APPROVED,
                    "counts": True,
                    "source_attempt_id": "ghost",
                    "target_requirement_id": self.calculus1["id"],
                    "target_requirement_name": self.calculus1["name"],
                    "target_credits": 3.0,
                    "approved_credits": 3.0,
                    "authority": "偽造核章",
                    "evidence_reference": "偽造證據",
                    "allocation_type": "shadow_reuse",
                    "validation_codes": ["OK"],
                }
            ]
        }
        forged_result = apply_equivalency_audit_to_report(report, forged_complete)
        self.assertEqual(forged_result["target"]["effective_total_completed"], 0.0)
        self.assertTrue(any(APPLY_PROVENANCE_REQUIRED in warning for warning in forged_result["policy_warnings"]))


if __name__ == "__main__":
    unittest.main()
