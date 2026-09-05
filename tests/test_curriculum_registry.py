import unittest

from curriculum_registry import (
    COMPLETE,
    CONFLICTED,
    MANUAL_REVIEW,
    MISSING,
    RESOLVED,
    VERIFIED,
    get_curriculum,
    list_curriculum_ids,
    resolve_rule_context,
)


class CurriculumRegistryTests(unittest.TestCase):
    def test_primary_and_target_are_distinct_versioned_curricula(self):
        primary = get_curriculum("primary:114:apc:chemistry")
        target = get_curriculum("target:double_major:114:apc:chemistry")

        self.assertEqual(primary["kind"], "primary")
        self.assertEqual(target["kind"], "double_major_target")
        self.assertNotEqual(primary["curriculum_id"], target["curriculum_id"])
        self.assertEqual(primary["version"], "114")
        self.assertEqual(target["version"], "114")
        self.assertEqual(primary["program"], "物化")
        self.assertEqual(target["program"], "物化")

    def test_only_admission_cohort_cannot_resolve_double_major_target(self):
        resolution = resolve_rule_context(
            {
                "admission_cohort": "114",
                "primary_program": "地生",
                "program_type": "雙主修",
                "target_program": "物化",
                "target_track": "化學組",
            }
        )

        target = resolution["dimensions"]["target_curriculum_version"]
        self.assertNotEqual(target["status"], RESOLVED)
        self.assertIsNone(target.get("value"))
        self.assertIn(resolution["blocker"], {MISSING, MANUAL_REVIEW})
        self.assertTrue(resolution["blockers"])

    def test_only_application_term_cannot_resolve_target(self):
        resolution = resolve_rule_context(
            {
                "application_term": "115-1",
                "primary_program": "地生",
                "program_type": "雙主修",
                "target_program": "資科",
            }
        )

        self.assertEqual(resolution["dimensions"]["admission_cohort"]["status"], MISSING)
        self.assertEqual(
            resolution["dimensions"]["target_curriculum_version"]["status"],
            MISSING,
        )
        self.assertNotEqual(resolution["status"], RESOLVED)

    def test_selected_target_version_requires_scoped_evidence(self):
        selected_only = resolve_rule_context(
            {
                "admission_cohort": "114",
                "primary_program": "地生",
                "program_type": "雙主修",
                "target_program": "資科",
                "target_curriculum_version": "114",
            }
        )
        self.assertEqual(
            selected_only["dimensions"]["target_curriculum_version"]["status"],
            MANUAL_REVIEW,
        )
        self.assertNotEqual(selected_only["status"], RESOLVED)

        evidenced = resolve_rule_context(
            {
                "admission_cohort": "114",
                "primary_program": "地生",
                "program_type": "雙主修",
                "target_program": "資科",
                "target_curriculum_version": "114",
                "target_version_evidence_reference": "registrar:114-1:target-curriculum",
            }
        )
        target = evidenced["dimensions"]["target_curriculum_version"]
        self.assertEqual(target["status"], MANUAL_REVIEW)
        self.assertEqual(target["evidence_reference"], "registrar:114-1:target-curriculum")
        self.assertFalse(evidenced["can_pass"])

        user_assertion_only = resolve_rule_context(
            {
                "admission_cohort": "114",
                "primary_program": "地生",
                "program_type": "雙主修",
                "target_program": "資科",
                "target_curriculum_version": "114",
                "scoped_applicability_assertion": {
                    "curriculum_id": "target:double_major:114:cs",
                    "admission_cohort": "114",
                    "target_program": "資科",
                    "scope": "student-specific approval",
                },
            }
        )
        self.assertEqual(
            user_assertion_only["dimensions"]["target_curriculum_version"]["status"],
            MANUAL_REVIEW,
        )
        self.assertFalse(user_assertion_only["can_pass"])

    def test_normalization_keeps_program_and_track_slugs_idempotent(self):
        for program, track in (
            ("apc", "chemistry"),
            ("apc", "physics"),
            ("earth", "life_science"),
            ("earth", "earth_environment"),
        ):
            with self.subTest(program=program, track=track):
                resolution = resolve_rule_context(
                    {
                        "admission_cohort": "114",
                        "primary_program": program,
                        "primary_track": track,
                        "program_type": "單主修",
                    }
                )
                self.assertEqual(
                    resolution["primary_curriculum"]["program_slug"],
                    program,
                )
                self.assertEqual(
                    resolution["primary_curriculum"]["track_slug"],
                    track,
                )

    def test_chemistry_group_never_falls_back_to_physics(self):
        resolution = resolve_rule_context(
            {
                "admission_cohort": "114",
                "primary_program": "物化",
                "primary_track": "化學組",
                "program_type": "雙主修",
                "target_program": "物化",
                "target_track": "化學組",
                "target_curriculum_version": "target:double_major:114:apc:chemistry",
            }
        )
        self.assertEqual(resolution["primary_curriculum"]["track_slug"], "chemistry")
        self.assertEqual(resolution["target_program"], "物化")
        self.assertEqual(resolution["target_track"], "應用化學")
        target = resolution["dimensions"]["target_curriculum_version"]
        self.assertEqual(target["curriculum_id"], "target:double_major:114:apc:chemistry")
        self.assertNotEqual(target["curriculum"].get("track_slug"), "physics")

    def test_target_id_must_be_double_major_target_and_match_scope(self):
        cases = (
            "primary:114:apc:chemistry",
            "target:double_major:114:cs",
            "target:double_major:114:apc:physics",
        )
        for selected_id in cases:
            with self.subTest(selected_id=selected_id):
                resolution = resolve_rule_context(
                    {
                        "admission_cohort": "114",
                        "primary_program": "地生",
                        "program_type": "雙主修",
                        "target_program": "物化",
                        "target_track": "化學組",
                        "target_curriculum_version": selected_id,
                    }
                )
                target = resolution["dimensions"]["target_curriculum_version"]
                self.assertIsNone(target.get("curriculum_id"))
                self.assertIsNone(target.get("curriculum"))
                self.assertNotEqual(target["status"], RESOLVED)
                self.assertFalse(resolution["can_pass"])

    def test_target_id_and_applicability_assertion_must_agree(self):
        resolution = resolve_rule_context(
            {
                "admission_cohort": "114",
                "primary_program": "地生",
                "program_type": "雙主修",
                "target_program": "資科",
                "target_curriculum_version": "target:double_major:114:cs",
                "scoped_applicability_assertion": {
                    "curriculum_id": "target:double_major:114:math",
                    "admission_cohort": "114",
                    "target_program": "數學",
                    "scope": "student-specific approval",
                },
            }
        )
        target = resolution["dimensions"]["target_curriculum_version"]
        self.assertIsNone(target.get("curriculum_id"))
        self.assertNotEqual(target["status"], RESOLVED)
        self.assertFalse(resolution["can_pass"])
        self.assertTrue(any("assertion" in item["reason"] for item in resolution["blockers"]))

    def test_server_owned_resolver_can_resolve_cross_cohort_target(self):
        calls = []

        def evidence_resolver(record_id):
            calls.append(record_id)
            return {
                "record_id": "approval-112-to-114-cs",
                "evidence_state": "VERIFIED",
                "curriculum_id": "target:double_major:114:cs",
                "admission_cohort": "112",
                "application_term": "112-2",
                "target_program": "資科",
                "target_track": None,
                "authority": "教務處",
                "evidence_reference": "official:approval:112-2",
            }

        resolution = resolve_rule_context(
            {
                "admission_cohort": "112",
                "primary_program": "地生",
                "program_type": "雙主修",
                "target_program": "資科",
                "target_curriculum_version": "target:double_major:114:cs",
                "application_term": "112-2",
                "target_version_evidence_reference": "approval-112-to-114-cs",
            },
            evidence_resolver=evidence_resolver,
        )
        target = resolution["dimensions"]["target_curriculum_version"]
        self.assertEqual(target["status"], RESOLVED)
        self.assertEqual(target["curriculum_id"], "target:double_major:114:cs")
        self.assertEqual(calls, ["approval-112-to-114-cs"])
        self.assertTrue(resolution["can_pass"])
        self.assertEqual(resolution["request"]["target_version_evidence_reference"], "approval-112-to-114-cs")
        self.assertNotIn("trusted_evidence_store", resolution["request"])
        self.assertNotIn("evidence_resolver", resolution["request"])

    def test_request_owned_fake_store_is_ignored_and_not_snapshotted(self):
        resolution = resolve_rule_context(
            {
                "admission_cohort": "114",
                "primary_program": "地生",
                "program_type": "雙主修",
                "target_program": "資科",
                "target_curriculum_version": "target:double_major:114:cs",
                "application_term": "114-1",
                "target_version_evidence_reference": "approval-114-cs",
                "trusted_evidence_store": {
                    "approval-114-cs": {
                        "record_id": "approval-114-cs",
                        "evidence_state": "VERIFIED",
                        "curriculum_id": "target:double_major:114:cs",
                        "admission_cohort": "114",
                        "application_term": "114-1",
                        "target_program": "資科",
                        "authority": "偽造的使用者資料",
                        "evidence_reference": "fake",
                    }
                },
            }
        )
        target = resolution["dimensions"]["target_curriculum_version"]
        self.assertEqual(target["status"], MANUAL_REVIEW)
        self.assertFalse(resolution["can_pass"])
        self.assertNotIn("trusted_evidence_store", resolution["request"])

    def test_injected_record_requires_exact_verified_fields(self):
        base_record = {
            "record_id": "approval-114-cs",
            "evidence_state": "VERIFIED",
            "curriculum_id": "target:double_major:114:cs",
            "admission_cohort": "114",
            "application_term": "114-1",
            "target_program": "資科",
            "target_track": None,
            "authority": "教務處",
            "evidence_reference": "official:approval:114-1",
        }
        invalid_records = {
            "missing_state": {**base_record, "evidence_state": None},
            "lowercase_state": {**base_record, "evidence_state": "verified"},
            "missing_cohort": {key: value for key, value in base_record.items() if key != "admission_cohort"},
            "missing_application": {key: value for key, value in base_record.items() if key != "application_term"},
            "missing_program": {key: value for key, value in base_record.items() if key != "target_program"},
            "missing_authority": {key: value for key, value in base_record.items() if key != "authority"},
            "missing_reference": {key: value for key, value in base_record.items() if key != "evidence_reference"},
        }
        for label, record in invalid_records.items():
            with self.subTest(record=label):
                resolution = resolve_rule_context(
                    {
                        "admission_cohort": "114",
                        "primary_program": "地生",
                        "program_type": "雙主修",
                        "target_program": "資科",
                        "target_curriculum_version": "target:double_major:114:cs",
                        "application_term": "114-1",
                        "target_version_evidence_reference": "approval-114-cs",
                    },
                    evidence_resolver=lambda _record_id, value=record: value,
                )
                self.assertNotEqual(
                    resolution["dimensions"]["target_curriculum_version"]["status"],
                    RESOLVED,
                )
                self.assertFalse(resolution["can_pass"])

    def test_injected_record_dimension_mismatches_are_blocked(self):
        base_record = {
            "record_id": "approval-114-cs",
            "evidence_state": "VERIFIED",
            "curriculum_id": "target:double_major:114:cs",
            "admission_cohort": "114",
            "application_term": "114-1",
            "target_program": "資科",
            "target_track": None,
            "authority": "教務處",
            "evidence_reference": "official:approval:114-1",
        }
        mismatches = {
            "cohort": {**base_record, "admission_cohort": "113"},
            "application_term": {**base_record, "application_term": "114-2"},
            "curriculum": {**base_record, "curriculum_id": "target:double_major:113:cs"},
            "program": {**base_record, "target_program": "數學"},
        }
        for label, record in mismatches.items():
            with self.subTest(record=label):
                resolution = resolve_rule_context(
                    {
                        "admission_cohort": "114",
                        "primary_program": "地生",
                        "program_type": "雙主修",
                        "target_program": "資科",
                        "target_curriculum_version": "target:double_major:114:cs",
                        "application_term": "114-1",
                        "target_version_evidence_reference": "approval-114-cs",
                    },
                    evidence_resolver=lambda _record_id, value=record: value,
                )
                self.assertNotEqual(
                    resolution["dimensions"]["target_curriculum_version"]["status"],
                    RESOLVED,
                )
                self.assertFalse(resolution["can_pass"])

    def test_evaluate_graduation_accepts_injected_resolver_without_snapshotting_it(self):
        from credit_engine import evaluate_graduation

        calls = []

        def evidence_resolver(record_id):
            calls.append(record_id)
            return {
                "record_id": record_id,
                "evidence_state": "VERIFIED",
                "curriculum_id": "target:double_major:114:cs",
                "admission_cohort": "112",
                "application_term": "112-2",
                "target_program": "資科",
                "target_track": None,
                "authority": "教務處",
                "evidence_reference": "official:approval:112-2",
            }

        report = evaluate_graduation(
            [],
            {
                "admission_cohort": "112",
                "primary_program": "地生",
                "program_type": "雙主修",
                "target_program": "資科",
                "target_curriculum_version": "target:double_major:114:cs",
                "application_term": "112-2",
                "target_version_evidence_reference": "approval-112-to-114-cs",
            },
            evidence_resolver=evidence_resolver,
        )
        target = report["rule_resolution"]["dimensions"]["target_curriculum_version"]
        self.assertEqual(target["status"], RESOLVED)
        self.assertEqual(calls, ["approval-112-to-114-cs"])
        self.assertNotIn("evidence_resolver", report["rule_resolution"]["request"])
        self.assertNotIn("trusted_evidence_store", report["rule_resolution"]["request"])
        self.assertNotEqual(report["summary"]["graduation_status"], "PASS")

    def test_111_and_115_earth_primary_catalogs_are_complete_and_source_backed(self):
        for cohort in ("111", "115"):
            curriculum = get_curriculum(f"primary:{cohort}:earth:earth_environment")
            self.assertEqual(curriculum["coverage_state"], COMPLETE)
            self.assertTrue(curriculum["course_catalog"])
            self.assertTrue(curriculum["pass_eligible"])
            self.assertTrue(curriculum["course_catalog"][0]["source_url"])
            self.assertEqual(curriculum["course_catalog"][0]["curriculum_version"], cohort)
            self.assertEqual(len(curriculum["university_requirements"]), 10)
            expected_non_credit = {
                "體育",
                "資訊應用與設計",
                "大學生活學習與輔導",
            }
            if cohort != "115":
                expected_non_credit.add("服務學習")
            self.assertEqual(len(curriculum["non_credit_requirements"]), len(expected_non_credit))
            self.assertEqual(
                {row["name"] for row in curriculum["non_credit_requirements"]},
                expected_non_credit,
            )
            self.assertNotIn(
                "大學生學習與生涯發展",
                {row["name"] for row in curriculum["course_catalog"]},
            )
            if cohort == "111":
                self.assertFalse(
                    any(row["name"] == "英文(三)" for row in curriculum["course_catalog"])
                )
            else:
                self.assertTrue(
                    any(row["name"] == "英文(三)" for row in curriculum["course_catalog"])
                )
            self.assertEqual(curriculum["non_credit_requirements"][0]["semesters_required"], 4)

    def test_unresolved_rule_gate_preserves_definite_academic_failure(self):
        from credit_engine import _apply_rule_resolution_gate

        unresolved = {"status": "UNKNOWN", "can_pass": False, "blockers": []}
        report = {
            "summary": {
                "graduation_status": "NOT_SATISFIED",
                "graduation_ready": True,
            }
        }

        result = _apply_rule_resolution_gate(report, unresolved)

        self.assertEqual(result["summary"]["graduation_status"], "NOT_SATISFIED")
        self.assertFalse(result["summary"]["graduation_ready"])

    def test_unresolved_rule_gate_downgrades_only_nondefinitive_statuses(self):
        from credit_engine import _apply_rule_resolution_gate

        unresolved = {"status": "UNKNOWN", "can_pass": False, "blockers": []}
        for prior_status in ("SATISFIED", "UNKNOWN"):
            with self.subTest(prior_status=prior_status):
                report = {
                    "summary": {
                        "graduation_status": prior_status,
                        "graduation_ready": True,
                    }
                }
                result = _apply_rule_resolution_gate(report, unresolved)
                self.assertEqual(result["summary"]["graduation_status"], "UNKNOWN")
                self.assertFalse(result["summary"]["graduation_ready"])

    def test_corrected_official_records_keep_assertions_and_pages(self):
        corrected_ids = {
            "target:double_major:113:math",
            "target:double_major:111:apc:chemistry",
            "target:double_major:112:apc:chemistry",
            "primary:114:math:math_scientific_computing",
            "primary:114:cs",
            "primary:115:cs",
        }
        for curriculum_id in corrected_ids:
            with self.subTest(curriculum_id=curriculum_id):
                curriculum = get_curriculum(curriculum_id)
                self.assertEqual(curriculum["evidence_state"], VERIFIED)
                self.assertGreaterEqual(len(curriculum["source_assertions"]), 2)
                self.assertTrue(all(item.get("source", {}).get("pages") for item in curriculum["source_assertions"]))

        cs114 = get_curriculum("primary:114:cs")
        stale_summary = next(
            item for item in cs114["source_assertions"] if item["id"] == "cs.primary.114.split8-16-4"
        )
        self.assertEqual(stale_summary["evidence_state"], CONFLICTED)
        self.assertFalse(stale_summary["blocks_decision"])
        # The conflicting summary row remains auditable, but its source
        # explicitly does not block the complete row-level catalogue.
        self.assertEqual(cs114["status"], VERIFIED)

        math113_dm = get_curriculum("target:double_major:113:math")
        moved_courses = {
            item["id"] for item in math113_dm["source_assertions"]
            if item["id"].endswith(("elective.high_calculus_1", "elective.algebra_1"))
        }
        self.assertEqual(
            moved_courses,
            {"math.dm.113.elective.high_calculus_1", "math.dm.113.elective.algebra_1"},
        )

        cs_target = get_curriculum("target:double_major:115:cs")
        self.assertEqual(cs_target["aggregate_status"], "VERIFIED")
        self.assertEqual(cs_target["coverage_state"], COMPLETE)
        self.assertTrue(cs_target["pass_eligible"])

    def test_math_111_112_double_major_minima_are_jointly_satisfiable(self):
        for cohort in ("111", "112"):
            with self.subTest(cohort=cohort):
                curriculum = get_curriculum(f"target:double_major:{cohort}:math")
                self.assertEqual(curriculum["evidence_state"], VERIFIED)
                self.assertEqual(curriculum["coverage_state"], COMPLETE)
                self.assertTrue(curriculum["pass_eligible"])
                self.assertEqual(curriculum["requirements"]["base_required"], 21)
                self.assertEqual(curriculum["requirements"]["other_required"], 18)
                self.assertEqual(curriculum["requirements"]["total_required"], 40)
                self.assertEqual(
                    {item["id"] for item in curriculum["source_assertions"]},
                    {
                        f"math.dm.{cohort}.total40",
                        f"math.dm.{cohort}.required21",
                        f"math.dm.{cohort}.elective18",
                    },
                )

    def test_math_primary_113_is_not_the_114_conflict(self):
        curriculum = get_curriculum("primary:113:math:math_scientific_computing")
        self.assertEqual(curriculum["evidence_state"], "VERIFIED")
        self.assertNotEqual(curriculum["status"], CONFLICTED)
        self.assertFalse(any("衝突" in warning for warning in curriculum["warnings"]))

    def test_double_major_requirements_use_40_credit_schema(self):
        for cohort in ("111", "112", "113", "114", "115"):
            with self.subTest(cohort=cohort):
                curriculum = get_curriculum(f"target:double_major:{cohort}:math")
                requirements = curriculum["requirements"]
                self.assertEqual(requirements["schema"], "double_major_40")
                self.assertEqual(requirements["total"], 40)
                self.assertEqual(requirements["total_required"], 40)
                self.assertIn("base_required", requirements)
                self.assertIn("other_required", requirements)
                self.assertNotEqual(requirements["total"], 128)

        math_114 = get_curriculum("target:double_major:114:math")
        self.assertEqual(math_114["requirements"]["base_required"], 14)
        self.assertEqual(math_114["requirements"]["other_required"], 26)
        self.assertEqual(math_114["coverage_state"], COMPLETE)
        self.assertTrue(math_114["pass_eligible"])
        self.assertTrue(all(item["id"].startswith("math.dm.114") for item in math_114["source_assertions"]))

        math_115 = get_curriculum("target:double_major:115:math")
        self.assertEqual(math_115["requirements"]["base_required"], 14)
        self.assertEqual(math_115["requirements"]["other_required"], 26)
        self.assertEqual(math_115["coverage_state"], COMPLETE)
        self.assertTrue(math_115["pass_eligible"])
        self.assertTrue(all(item["id"].startswith("math.dm.115") for item in math_115["source_assertions"]))

    def test_math_113_double_major_moves_two_rows_to_elective_pool(self):
        curriculum = get_curriculum("target:double_major:113:math")
        named = [row for row in curriculum["course_catalog"] if row["kind"] == "course"]
        quotas = [row for row in curriculum["course_catalog"] if row["kind"] == "quota"]
        self.assertEqual({row["name"] for row in named}, {"微積分(一)", "微積分(二)", "線性代數(一)", "線性代數(二)"})
        self.assertEqual(sum(row["credits"] for row in named), 14)
        self.assertEqual(len(quotas), 1)
        self.assertEqual(quotas[0]["required_credits"], 26)
        self.assertTrue({"高等微積分(一)", "代數學(一)"} <= set(quotas[0]["eligible_course_names"]))

    def test_apc_111_112_chemistry_target_keeps_additional_quota_verified(self):
        for cohort in ("111", "112"):
            with self.subTest(cohort=cohort):
                curriculum = get_curriculum(f"target:double_major:{cohort}:apc:chemistry")
                self.assertEqual(curriculum["evidence_state"], VERIFIED)
                self.assertEqual(curriculum["coverage_state"], COMPLETE)
                named_rows = [row for row in curriculum["course_catalog"] if row["kind"] == "course"]
                quota = next(row for row in curriculum["course_catalog"] if row["kind"] == "quota")
                self.assertEqual(sum(row["credits"] for row in named_rows), 16.0)
                self.assertEqual(quota["credits"], 24.0)
                self.assertEqual(quota["evidence_state"], VERIFIED)
                self.assertEqual(quota["coverage_state"], COMPLETE)
                target_pool = curriculum["course_pools"][quota["eligible_pool_ids"][0]]
                self.assertTrue(target_pool["candidate_courses"])

    def test_target_catalog_coverage_cannot_claim_complete_without_semantics(self):
        for curriculum_id in (
            "target:double_major:112:cs",
            "target:double_major:113:cs",
            "target:double_major:114:cs",
            "target:double_major:115:apc:chemistry",
            "target:double_major:115:apc:physics",
        ):
            with self.subTest(curriculum_id=curriculum_id):
                curriculum = get_curriculum(curriculum_id)
                self.assertEqual(curriculum["coverage_state"], COMPLETE)
                self.assertTrue(curriculum["pass_eligible"])
                self.assertTrue(curriculum["course_catalog"])
                for row in curriculum["course_catalog"]:
                    self.assertEqual(row["evidence_state"], VERIFIED)
                    if row["kind"] == "quota":
                        self.assertTrue(row["eligible_course_names"])

    def test_complete_catalogs_have_executable_semantics_and_no_candidate_requirements(self):
        """A COMPLETE record has rows, while pool candidates stay candidates."""

        required_row_fields = {"name", "credits", "bucket", "choice_group", "track", "is_zero_credit"}
        complete_ids = []
        pass_eligible_ids = []
        for curriculum_id in list_curriculum_ids():
            curriculum = get_curriculum(curriculum_id)
            # Minor targets may be COMPLETE when their named course rows are
            # fully sourced.  This legacy invariant is scoped to the
            # pre-minor catalog records; minor qualification still has its
            # separate evidence gates in graduation_service.
            if curriculum["kind"] == "minor_target":
                continue
            if curriculum["pass_eligible"]:
                pass_eligible_ids.append(curriculum_id)
            if curriculum["coverage_state"] != COMPLETE:
                continue
            complete_ids.append(curriculum_id)
            self.assertTrue(curriculum["pass_eligible"], curriculum_id)
            self.assertTrue(curriculum["course_catalog"], curriculum_id)
            self.assertTrue(
                all(required_row_fields.issubset(row) for row in curriculum["course_catalog"]),
                curriculum_id,
            )

        expected_complete = {
            f"primary:{cohort}:earth:{track}"
            for cohort in ("111", "112", "113", "114", "115")
            for track in ("earth_environment", "life_science")
        }
        expected_complete.update(
            f"primary:{cohort}:apc:{track}"
            for cohort in ("111", "112", "113", "114", "115")
            for track in ("physics", "chemistry")
        )
        expected_complete.update(
            {
                "primary:111:math",
                "primary:112:math",
                *(
                    f"primary:{cohort}:math:{track}"
                    for cohort in ("113", "114")
                    for track in ("math_scientific_computing", "data_science", "math_education")
                ),
                "primary:115:math:math_scientific_computing",
                "primary:115:math:data_science",
            }
        )
        expected_complete.update(f"primary:{cohort}:cs" for cohort in ("111", "112", "113", "114", "115"))
        expected_complete.update(
            f"target:double_major:{cohort}:{program}"
            for cohort in ("111", "112", "113", "114", "115")
            for program in ("earth:earth_environment", "earth:life_science", "apc:physics", "apc:chemistry", "cs", "math")
        )
        self.assertEqual(set(complete_ids), expected_complete)
        self.assertEqual(set(pass_eligible_ids), expected_complete)

    def test_cs_primary_catalogs_enable_registry_resolution(self):
        primary_contexts = (
            ("112", "資科", None, "primary:112:cs"),
            ("113", "資科", None, "primary:113:cs"),
        )
        for cohort, program, track, curriculum_id in primary_contexts:
            with self.subTest(cohort=cohort, program=program):
                curriculum = get_curriculum(curriculum_id)
                self.assertEqual(curriculum["coverage_state"], "COMPLETE")
                self.assertTrue(curriculum["pass_eligible"])
                request = {
                    "admission_cohort": cohort,
                    "primary_program": program,
                    "program_type": "單主修",
                }
                if track is not None:
                    request["primary_track"] = track
                resolution = resolve_rule_context(request)
                self.assertTrue(resolution["can_pass"])
                self.assertEqual(
                    resolution["dimensions"]["primary_curriculum"]["status"],
                    "RESOLVED",
                )

    def test_evaluator_blocks_false_resolution_even_when_blockers_are_empty(self):
        from unittest.mock import patch

        from credit_engine import evaluate_cohort_plan

        with patch(
            "credit_engine.resolve_rule_context",
            return_value={"can_pass": False, "blockers": [], "blocker_codes": [], "dimensions": {}},
        ):
            report = evaluate_cohort_plan(
                [],
                {
                    "admission_cohort": "114",
                    "primary_program": "地生",
                    "program_type": "單主修",
                },
            )

        self.assertTrue(report["rule_resolution_blocked"])
        self.assertFalse(report["summary"]["graduation_ready"])
        self.assertFalse(report["graduation_gates"]["rule_resolution"])

    def test_resolution_exposes_primary_and_target_dimensions(self):
        resolution = resolve_rule_context(
            {
                "admission_cohort": "114",
                "primary_program": "地生",
                "primary_track": "地球環境",
                "program_type": "雙主修",
                "target_program": "資科",
                "target_curriculum_version": "114",
                "scoped_applicability_assertion": {
                    "curriculum_id": "target:double_major:114:cs",
                    "admission_cohort": "114",
                    "target_program": "資科",
                    "scope": "student-specific approval",
                },
            }
        )

        self.assertIn("primary_curriculum", resolution["dimensions"])
        self.assertIn("target_curriculum_version", resolution["dimensions"])
        self.assertEqual(resolution["primary_curriculum"]["kind"], "primary")
        self.assertEqual(resolution["target_curriculum"]["kind"], "double_major_target")
        self.assertNotEqual(
            resolution["primary_curriculum"]["curriculum_id"],
            resolution["target_curriculum"]["curriculum_id"],
        )

    def test_evaluate_graduation_legacy_handbook_year_does_not_select_target(self):
        from credit_engine import evaluate_graduation

        report = evaluate_graduation(
            [],
            {
                "domain": "地球環境",
                "program": "雙主修",
                "target_dept": "物化系化學組",
                "handbook_year": "114",
            },
        )

        target = report["rule_resolution"]["dimensions"]["target_curriculum_version"]
        self.assertNotEqual(target["status"], RESOLVED)
        self.assertFalse(report["summary"]["graduation_ready"])
        self.assertNotEqual(report["summary"]["graduation_status"], "PASS")
        self.assertIn(report["rule_resolution"]["blocker"], {MISSING, MANUAL_REVIEW})

    def test_evaluate_cohort_plan_blocks_unverified_individual_target_evidence(self):
        from credit_engine import evaluate_graduation

        report = evaluate_graduation(
            [],
            {
                "admission_cohort": "115",
                "primary_program": "地生",
                "program_type": "雙主修",
                "target_program": "資科",
                "target_curriculum_version": "115",
                "application_term": "115-1",
                "target_version_evidence_reference": "registrar:115-1:target-curriculum",
            },
        )

        target = report["rule_resolution"]["dimensions"]["target_curriculum_version"]
        self.assertEqual(target["status"], MANUAL_REVIEW)
        self.assertEqual(target["coverage_state"], COMPLETE)
        self.assertFalse(report["summary"]["graduation_ready"])
        self.assertNotEqual(report["summary"]["graduation_status"], "PASS")
        self.assertTrue(any(item["code"] == MANUAL_REVIEW for item in report["rule_resolution"]["blockers"]))

    def test_apc_chemistry_double_major_catalogs_are_cohort_specific(self):
        expected_named_rows = {
            "113": [
                ("普通物理學(一)", 3.0),
                ("普通物理實驗(一)", 1.0),
                ("普通化學(一)", 3.0),
                ("普通化學實驗(一)", 1.0),
                ("普通物理學(二)", 3.0),
                ("普通物理實驗(二)", 1.0),
                ("普通化學(二)", 3.0),
                ("普通化學實驗(二)", 1.0),
            ],
            "114": [
                ("普通物理學(一)", 3.0),
                ("普通物理實驗(一)", 1.0),
                ("普通化學(一)", 3.0),
                ("普通化學實驗(一)", 1.0),
                ("普通物理學(二)", 3.0),
                ("普通物理實驗(二)", 1.0),
                ("普通化學(二)", 3.0),
                ("普通化學實驗(二)", 1.0),
            ],
            "115": [
                ("普通物理學(一)", 3.0),
                ("普通化學(一)", 3.0),
                ("普通化學實驗(一)", 1.0),
                ("微積分(一)", 3.0),
                ("普通物理學(二)", 3.0),
                ("普通化學(二)", 3.0),
                ("普通化學實驗(二)", 1.0),
                ("微積分(二)", 3.0),
            ],
        }

        for cohort, expected in expected_named_rows.items():
            with self.subTest(cohort=cohort):
                curriculum = get_curriculum(f"target:double_major:{cohort}:apc:chemistry")
                named = [
                    (row["name"], float(row["credits"]))
                    for row in curriculum["course_catalog"]
                    if row.get("kind") == "course"
                ]
                self.assertCountEqual(named, expected)
                self.assertEqual(curriculum["coverage_state"], COMPLETE)
                self.assertTrue(curriculum["pass_eligible"])

        self.assertNotIn(
            "微積分(一)",
            [row["name"] for row in get_curriculum("target:double_major:113:apc:chemistry")["course_catalog"]],
        )
        self.assertNotIn(
            "微積分(二)",
            [row["name"] for row in get_curriculum("target:double_major:114:apc:chemistry")["course_catalog"]],
        )

    def test_apc_chemistry_catalog_rows_keep_lecture_lab_and_provenance(self):
        expected_components = {
            "普通物理學(一)": "lecture",
            "普通物理實驗(一)": "lab",
            "普通化學(一)": "lecture",
            "普通化學實驗(一)": "lab",
            "普通物理學(二)": "lecture",
            "普通物理實驗(二)": "lab",
            "普通化學(二)": "lecture",
            "普通化學實驗(二)": "lab",
            "微積分(一)": "lecture",
            "微積分(二)": "lecture",
        }
        required_fields = {
            "name",
            "raw_title",
            "credits",
            "bucket",
            "requirement_id",
            "kind",
            "component",
            "track",
            "cohort",
            "choice_group",
            "is_zero_credit",
            "evidence_state",
            "assertion_id",
            "source_reference",
            "source",
            "provenance",
        }

        for cohort in ("113", "114", "115"):
            with self.subTest(cohort=cohort):
                curriculum = get_curriculum(f"target:double_major:{cohort}:apc:chemistry")
                rows = curriculum["course_catalog"]
                self.assertTrue(rows)
                self.assertTrue(
                    all(required_fields.issubset(row) for row in rows),
                    [row for row in rows if not required_fields.issubset(row)],
                )
                for row in rows:
                    self.assertEqual(row["cohort"], cohort)
                    self.assertEqual(row["track"], "chemistry")
                    self.assertEqual(row["evidence_state"], "VERIFIED")
                    self.assertTrue(row["source_reference"])
                    self.assertTrue(row["source"].get("url"))
                    self.assertTrue(row["source"].get("pages"))
                    self.assertEqual(row["provenance"]["assertion_id"], row["assertion_id"])
                    if row["kind"] == "course":
                        self.assertEqual(row["bucket"], "base")
                        self.assertEqual(row["component"], expected_components[row["name"]])
                        self.assertEqual(row["choice_group"], None)
                    else:
                        self.assertEqual(row["kind"], "quota")
                        self.assertEqual(row["bucket"], "remainder_required")
                        self.assertEqual(row["component"], "quota")
                        self.assertTrue(row["eligible_course_names"])

    def test_apc_chemistry_catalog_aggregates_do_not_double_count_rows(self):
        for cohort, base, other in (("113", 16.0, 24.0), ("114", 16.0, 24.0), ("115", 20.0, 20.0)):
            with self.subTest(cohort=cohort):
                curriculum = get_curriculum(f"target:double_major:{cohort}:apc:chemistry")
                rows = curriculum["course_catalog"]
                requirement_ids = [row["requirement_id"] for row in rows]
                identities = [row["official_course_identity"] for row in rows]
                self.assertEqual(len(requirement_ids), len(set(requirement_ids)))
                self.assertEqual(len(identities), len(set(identities)))
                named_credits = sum(
                    float(row["credits"]) for row in rows if row.get("kind") == "course"
                )
                quota_rows = [row for row in rows if row.get("kind") == "quota"]
                self.assertEqual(len(quota_rows), 1)
                self.assertEqual(named_credits, base)
                self.assertEqual(float(quota_rows[0]["credits"]), other)
                self.assertEqual(named_credits + float(quota_rows[0]["credits"]), 40.0)
                self.assertEqual(curriculum["requirements"]["base_required"], base)
                self.assertEqual(curriculum["requirements"]["other_required"], other)
                self.assertEqual(curriculum["requirements"]["total_required"], 40)

    def test_apc_115_chemistry_catalog_excludes_legacy_rows_and_is_deterministic(self):
        first = get_curriculum("target:double_major:115:apc:chemistry")
        second = get_curriculum("target:double_major:115:apc:chemistry")
        self.assertEqual(first, second)
        names = [row["name"] for row in first["course_catalog"]]
        self.assertEqual(names.count("微積分(一)"), 1)
        self.assertEqual(names.count("微積分(二)"), 1)
        self.assertNotIn("普通物理實驗(一)", names)
        self.assertNotIn("普通物理實驗(二)", names)
        self.assertNotIn("化學數學(一)", names)
        self.assertNotIn("應用科學專題(一)", names)
        self.assertNotIn("應用科學專題(二)", names)
        quota = next(row for row in first["course_catalog"] if row["kind"] == "quota")
        self.assertTrue(quota["eligible_course_names"])
        self.assertEqual(quota["evidence_state"], VERIFIED)


if __name__ == "__main__":
    unittest.main()
