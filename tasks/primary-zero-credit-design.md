# Primary required zero-credit course contract

## Assessment

The official primary-program tables support deterministic zero-credit gates without marking an entire curriculum `PARTIAL`. For APC, Earth, Math, and CS, `大學生活學習與輔導` is an operative required-course series of eight distinct terms in cohorts 111–115. `服務學習` has narrower, source-specific applicability: APC and Earth 111–114, Math 111–112, and CS 111–113. Later omissions and the Math 113 strike-through are operative removals, so those cohorts must not receive a service-learning gate.

The existing registry/service shape is sufficient except for one small trust fix. Department zero-credit rows already flow from `_course_catalog()` into `non_credit_requirements` (`curriculum_registry.py:4490-4510`), and `_non_credit_requirement_result()` already enforces count, distinct term, completion state, and per-student UNKNOWN (`graduation_service.py:2982-3318`). However, its zero-credit filter is deliberately disabled for `OFFICIAL_LISTED_COURSE_COMPLETION` (`graduation_service.py:3110-3117`). Add an explicit `require_zero_credits` check for that kind before using server-owned course membership.

## Operative source matrix

| Program | Cohort | Life guidance | Service learning | Official primary-table evidence |
|---|---:|---:|---:|---|
| APC, physics and chemistry tracks | 111–114 | 8 distinct terms | 2 distinct terms | `tmp/handbook_official_111.pdf` pp. 6, 15; 112 pp. 6, 15; 113 pp. 7, 18; 114 pp. 8, 19. The required tables show life guidance in years 1–4, both semesters, 0 credits and 1 hour; service learning in year 2, both semesters, 0 credits. The service note requires at least 24 hours per semester, including at least 12 hours of public-interest service. |
| APC, physics and chemistry tracks | 115 | 8 distinct terms | not applicable | `tmp/handbook_official_115.pdf` pp. 8, 20. Life guidance remains in all eight semester cells; the required table no longer contains service learning. |
| Earth | 111–114 | 8 distinct terms | 2 distinct terms | 111 pp. 27, 31–32; 112 pp. 27, 31–32; 113 pp. 32, 36, 38; 114 pp. 33, 40. The tables state years 1–4, total eight semesters. The 111–113 notes expressly require two semesters of service learning; the 114 required year-course row is 0+0 across both year-2 semesters. No department-page hourly minimum was found. |
| Earth | 115 | 8 distinct terms | not applicable | 115 pp. 41, 48. The life-guidance table says years 1–4, total eight semesters. Service learning is absent from the operative module and required table. |
| Math | 111–112 | 8 distinct terms | 2 distinct terms | 111 p. 70; 112 p. 65. The required tables show eight life-guidance semester cells. Service learning spans both year-2 semesters; its note requires at least 24 hours per semester, including at least 12 hours of public-interest service. |
| Math | 113–115 | 8 distinct terms | not applicable | 113 p. 67 (`tmp/math-113-required-67.png`) strikes the whole service-learning row and note; 114 pp. 71–72 (`tmp/math-114-required-72.png`) and 115 p. 82 omit it. Life guidance remains an eight-semester required series. The nearby `計算機概論` → `資訊科學與科學計算` amendment concerns a credit-bearing course and is outside this contract. |
| CS | 111–113 | 8 distinct terms | 2 distinct terms | 111 pp. 115–117; 112 pp. 110–112; 113 pp. 107–108. The tables list `大學生活學習與輔導 Part 1` through `Part 8`, each 0 credits/1 hour, and two year-2 service rows, each 0 credits/24 hours. The note requires at least 12 of the 24 hours per semester to be public-interest service. |
| CS | 114–115 | 8 distinct terms | not applicable at department-table scope | 114 pp. 111–112; 115 pp. 122–123. Part 1–8 remain required; no service-learning row appears. A separate university-wide policy could change this only after its cohort/program applicability is sourced; a generic architecture label is insufficient. |

“Not applicable” means the compiler emits no active requirement row for that cohort. Preserve the source fact as amendment/provenance metadata if useful, but never emit a `required=false` placeholder into a set the UI could mistake for pending work.

## Executable data contract

Emit one aggregate life-guidance descriptor per primary curriculum and, only for the applicable cells above, one aggregate service-learning descriptor. APC descriptors are track-scoped to both official primary tracks even though their constraints are identical.

```yaml
requirement_id: "<program>.primary.<cohort>.<track>.life_guidance"
name: "大學生活學習與輔導"
kind: "OFFICIAL_LISTED_COURSE_COMPLETION"
requirement_type: "non_credit_course_series"
required_count: 8
distinct_term_required: true
max_completions_per_term: 1
require_zero_credits: true
completion_statuses: ["COMPLETED"]
membership_id: "<server-owned, cohort/program/track-bound membership>"
applicable_curriculum_version: "<cohort>"
applicable_program_slug: "<program>"
applicable_track_slug: "<canonical track, APC/Earth only>"
evidence_state: "VERIFIED"
coverage_state: "COMPLETE"
scope_state: "VERIFIED"
automatic_decision: true
affects_credit_ledger: false
```

The `applicable_*` fields scope registry selection; they are not attempt attributes. The membership ID itself is server-owned and scoped to that compiled requirement. Do not set the evaluator's current `program_slug`, `track_slug`, or `membership_version_required` fields unless the attempt adapter supplies those values from official course identity, because `graduation_service.py:3160-3192` otherwise converts absent attempt metadata into a false UNKNOWN. Math and CS have no primary track axis, so their requirement IDs may use `department` as a stable ID segment but must omit an attempt-level track constraint. APC and Earth retain their actual curriculum track only at applicability/membership scope.

The membership contains only the official zero-credit life-guidance identities. For CS it includes Part 1–8. For the other programs it may include the repeated generic title, but a match still needs verified server-owned membership and an academic term. Do not accept a user-supplied category or title alone. If the official transcript/catalogue omits the part suffix, the server adapter may map that exact term-bound zero-credit identity to the aggregate membership; it must not add a fuzzy global alias.

Service learning uses the same shape with `required_count: 2`, `distinct_term_required: true`, `max_completions_per_term: 1`, and a service-specific membership. For APC 111–114, Math 111–112, and CS 111–113, also publish:

```yaml
required_hours: 48
hours_per_completion: 24
minimum_public_service_hours_per_completion: 12
hours_evidence_semantics: "official_course_completion_certifies_policy_minimum"
```

Those numbers describe the official completion standard. They are not student-entered or measured hours. An official `COMPLETED` course record certifies that the course requirements were met; enrollment or `IN_PROGRESS` does not. Earth 111–114 emits no hourly fields because its reviewed department pages prove two semester completions but do not prove a numeric hourly minimum.

Each descriptor carries the exact PDF page, printed page if different, original clause, source file/URL, assertion ID, and amendment action where relevant. Math 113 records `amendment_action: DELETE` for provenance but emits no service gate. APC/Earth 115 and CS 114/115 use scoped omission provenance rather than an invented deletion date.

## Minimal runtime action

1. Add the source-backed rows to the per-cohort primary catalogue or a dedicated primary non-credit builder. Prefer the dedicated builder because these are aggregate series, while `_primary_course_row()` currently produces a single-course default count and merely flags `is_zero_credit` (`curriculum_registry.py:1876-1980`). Continue returning them through the existing `non_credit_requirements` field.
2. In `_non_credit_requirement_result()`, define zero-credit enforcement as true when `require_zero_credits` is true, including direct official-list completion. Apply it before course identity/membership evaluation (`graduation_service.py:3110-3141`). A positive-credit same-name course then cannot satisfy the gate.
3. Reuse the existing official membership and verified identity checks (`graduation_service.py:3041-3072`, `3137-3197`). Curriculum/program/track applicability is fixed when the registry compiles the requirement; attempt-level binding is enabled only where the official adapter supplies the corresponding attempt fields. Missing or unresolved required membership, identity, version, or term produces UNKNOWN for this gate only. With complete attempt history and no eligible completed row, the result is FAIL. Do not change the curriculum’s source coverage to `PARTIAL` because one student lacks evidence.
4. Keep `affects_credit_ledger: false`; these gates observe completion attempts and never allocate, consume, create, or duplicate credits. The graduation decision must still include their result, so a credit-complete student missing an applicable course cannot PASS.

No new solver, waiver mechanism, or total-credit bucket is required. The existing count and distinct-term selection already prevents duplicate attempts or two rows in one semester from satisfying multiple required terms (`graduation_service.py:3209-3286`).

## Validation plan

1. Registry matrix: for every cohort/track, assert life count 8; assert service presence only for APC/Earth 111–114, Math 111–112, and CS 111–113. Confirm later cohorts have no active service gate.
2. Life series: eight verified zero-credit completions in eight terms PASS; seven FAIL; duplicate rows in one term count once; a missing term or unresolved official identity/membership yields UNKNOWN only for this requirement.
3. Service series: two verified completions in different terms PASS. One completion FAIL. Two rows in one term count once. APC/Math/CS expose 48/24/12 as policy provenance; Earth does not synthesize hours.
4. Amendment: Math 113 service attempts neither satisfy nor create a requirement; the life-guidance count remains 8. Check 114/115 Math likewise omit service.
5. Trust boundary: a positive-credit course with the same title, a user-authored membership/category, a wrong cohort/program/track/version membership, and an `IN_PROGRESS` row cannot PASS. The positive-credit case specifically guards the current direct-completion gap.
6. Conservation: adding these rows does not alter any allocated or earned-credit total, but an otherwise credit-complete primary scenario is blocked by an applicable missing zero-credit gate.

## Delegation

Implementation belongs to `terra_worker`: add the bounded registry descriptors and the one evaluator predicate, then add the matrix and counterexample tests above. A `luna_worker` may independently run the focused registry/service tests afterward.

## Caveats

The reviewed Earth department pages do not establish numeric service hours, so only its two-term completion count is automatic. CS 114/115 service learning is not supported by the reviewed department mandatory tables; any university-wide override requires a separately versioned, program-applicable official source rather than inference from older cohorts.

## Addendum: applicability, waiver, and course-membership scope

The IT completion requirement exposes a general scope collision in the current evaluator. `program_slug`, `track_slug`, and `curriculum_version` describe the student's applicable curriculum and are correctly required when matching a formal waiver (`graduation_service.py:2897-2978`). The direct-completion path also treats those same fields as properties of the completed course (`graduation_service.py:3152-3219`). A university GE course can have an empty or different offering program while validly satisfying an Earth student's IT requirement, so reusing student scope as course-offering scope creates a permanent UNKNOWN.

Use the following backward-compatible split rather than removing strict waiver binding:

```yaml
# Requirement applicability; selected by the trusted registry.
program_slug: earth
track_slug: earth_environment
curriculum_version: "115"

# Formal waiver scope; explicit fields take precedence, legacy fallback shown below.
waiver_program_slug: earth
waiver_track_slug: earth_environment
waiver_requirement_version: "115"
waiver_authority_ids: ["official:genedu"]

# Whether the completed COURSE ATTEMPT must carry matching offering metadata.
membership_program_required: false
membership_track_required: false
membership_version_required: false
```

`_non_credit_waiver_matches()` resolves expected waiver scope as follows:

1. `waiver_requirement_version`, falling back to the existing `curriculum_version/version/requirement_version` chain.
2. `waiver_program_slug`, falling back to the existing `program_slug/program` chain.
3. `waiver_track_slug`, falling back to the existing `track_slug/track` chain.

It continues to require subject, target requirement ID, verified evidence, allowed authority, evidence reference, and exact version/program/track. Empty expected waiver scope remains fail closed. The new fields do not weaken any existing waiver record.

The direct-completion path compares `attempt.program_slug`, `attempt.track_slug`, or `attempt.curriculum_version` only when the corresponding membership flag is true. For backward compatibility:

- `membership_program_required` defaults to true when a legacy row contains `program_slug` or `program`.
- `membership_track_required` defaults to true when a legacy row contains `track_slug` or `track`.
- Existing `membership_version_required` behavior is unchanged and defaults to false unless currently enabled by that field or `term_bound`.

The formal university IT row explicitly sets all three membership flags false. Its official course-list membership remains mandatory and server-owned; the term-bound membership record and trusted source still determine whether the course is on the approved list. Disabling an offering-program comparison therefore does not permit a user category override or an arbitrary same-name course. If a future department-only listed-course rule genuinely depends on the offering department or version recorded on the attempt, it sets the relevant flag true.

These fields are registry policy only. The attempt/request sanitizer must not accept them from student input, course metadata overrides, or UI form values. `applicable_*` aliases from the earlier contract may remain descriptive, but the three legacy applicability fields above remain authoritative until the surrounding registry is migrated; the evaluator must not use `applicable_*` as attempt predicates.

Targeted compatibility tests:

1. Preserve the existing legacy test: a row with `program_slug/track_slug` and no new flags still rejects an attempt with the wrong values.
2. An Earth IT row with the three waiver/applicability fields and membership program/track/version flags false accepts a verified, term-bound official GE membership even when the attempt offering program is empty or non-Earth.
3. The same row rejects missing, legacy, unverified, or wrong official membership and cannot accept a user-supplied category.
4. An approved waiver still rejects wrong or missing subject, requirement version, program, track, authority, and evidence reference, even though course-membership flags are false.
5. A department-only direct-completion fixture with membership program/track flags true rejects a course from another offering scope.
