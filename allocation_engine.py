"""Deterministic, evidence-aware credit allocation primitives.

The allocator is intentionally independent from the existing graduation
engine.  It operates on immutable value objects and returns a complete,
auditable result: exclusive allocations conserve transcript credits, while
approved shared-credit mappings are represented separately as shadow rows.
Unknown evidence is never promoted to a passing result.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"

VERIFIED = "VERIFIED"
CONFLICTED = "CONFLICTED"
MISSING = "MISSING"
MANUAL_REVIEW = "MANUAL_REVIEW"

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
NONE = "NONE"

LECTURE = "LECTURE"
LAB = "LAB"
COMBINED = "COMBINED"
WAIVER = "WAIVER"

EXCLUSIVE = "EXCLUSIVE"
SHARED_SHADOW = "SHARED_SHADOW"
SHARED_BLOCKED = "SHARED_BLOCKED"

BEST_ATTEMPT_ONLY = "BEST_ATTEMPT_ONLY"
REPEATABLE = "REPEATABLE"

PRIMARY_TO_TARGET = "PRIMARY_TO_TARGET"
TARGET_TO_PRIMARY = "TARGET_TO_PRIMARY"
SHARED_LIMIT = Decimal("6")

_ZERO = Decimal("0")
_DIAGNOSTIC_ID_PREFIXES = (
    "DUPLICATE_BINDING_ID:",
    "DUPLICATE_WAIVER_DECISION_ID:",
    "EQUIVALENCY_UNRESOLVED:",
    "EVIDENCE_UNRESOLVED:",
    "UNVERIFIED_EQUIVALENCY:",
    "UNVERIFIED_WAIVER:",
    "SHARED_SCOPE_UNKNOWN:",
    "SHARED_SOURCE_USE_UNKNOWN:",
    "SHARED_SOURCE_CAP:",
    "SHARED_CAPACITY_UNKNOWN:",
    "SHARED_LEDGER_CAP:",
)


def _decimal(value: Any, default: Decimal = _ZERO) -> Decimal:
    if isinstance(value, Decimal):
        result = value
    else:
        try:
            result = Decimal(str(value)) if value not in (None, "") else default
        except (InvalidOperation, TypeError, ValueError):
            return default
    if not result.is_finite():
        return default
    return result


def _nonnegative_decimal(value: Any, default: Decimal = _ZERO) -> Decimal:
    return max(_ZERO, _decimal(value, default))


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float, bool)) else ""


def _norm_status(value: Any) -> str:
    text = _text(value).upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "PASS": PASS,
        "PASSED": PASS,
        "COMPLETE": PASS,
        "COMPLETED": PASS,
        "IN_PROGRESS": "IN_PROGRESS",
        "CURRENT": "IN_PROGRESS",
        "TAKING": "IN_PROGRESS",
        "FAIL": FAIL,
        "FAILED": FAIL,
        "WITHDRAWN": FAIL,
        "WAIVER": WAIVER,
        "WAIVED": WAIVER,
        "UNKNOWN": UNKNOWN,
        "MANUAL_REVIEW": MANUAL_REVIEW,
        "CONFLICTED": CONFLICTED,
        "MISSING": MISSING,
    }
    return aliases.get(text, text or UNKNOWN)


def _norm_evidence_state(value: Any) -> str:
    text = _text(value).upper().replace("-", "_").replace(" ", "_")
    return text if text in {VERIFIED, CONFLICTED, MISSING, MANUAL_REVIEW} else UNKNOWN


def _norm_coverage(value: Any) -> str:
    text = _text(value).upper().replace("-", "_").replace(" ", "_")
    return text if text in {COMPLETE, PARTIAL, NONE} else NONE


def _norm_course_kind(value: Any) -> str:
    text = _text(value).upper().replace("-", "_").replace(" ", "_")
    if any(token in text for token in ("COMBINED", "LECTURE_LAB", "合併", "綜合")):
        return COMBINED
    if any(token in text for token in ("LAB", "實驗", "實習")):
        return LAB
    if any(token in text for token in ("LECTURE", "講授", "理論", "COURSE")):
        return LECTURE
    # Missing or unrecognised component metadata cannot be safely treated as
    # a lecture: doing so could make a lecture satisfy a lab requirement.
    return UNKNOWN


def _norm_repeat_policy(value: Any, repeatable: bool = False) -> str:
    if repeatable:
        return REPEATABLE
    text = _text(value).upper().replace("-", "_").replace(" ", "_")
    return REPEATABLE if text in {REPEATABLE, "ALLOW_REPEAT", "REPEATABLE_ATTEMPTS"} else BEST_ATTEMPT_ONLY


def _norm_direction(value: Any) -> str:
    text = _text(value).upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "PRIMARY_TO_TARGET": PRIMARY_TO_TARGET,
        "PRIMARY2TARGET": PRIMARY_TO_TARGET,
        "HOME_TO_TARGET": PRIMARY_TO_TARGET,
        "TARGET_TO_PRIMARY": TARGET_TO_PRIMARY,
        "TARGET2PRIMARY": TARGET_TO_PRIMARY,
        "SECONDARY_TO_PRIMARY": TARGET_TO_PRIMARY,
    }
    return aliases.get(text, text if text in {PRIMARY_TO_TARGET, TARGET_TO_PRIMARY} else "")


def _tuple_text(values: Any, *, preserve_order: bool = False) -> tuple[str, ...]:
    if values in (None, ""):
        return ()
    if isinstance(values, str):
        values = (values,)
    if not isinstance(values, Sequence) or isinstance(values, (bytes, bytearray)):
        return ()
    unique = {_text(item) for item in values}
    unique.discard("")
    return tuple(item for item in (values if preserve_order else sorted(unique)) if _text(item) in unique) if preserve_order else tuple(sorted(unique))


def _stable_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _safe_diagnostic(value: Any) -> str:
    """Mask opaque evidence/binding references in public diagnostics."""

    text = _text(value)
    for prefix in _DIAGNOSTIC_ID_PREFIXES:
        if text.startswith(prefix):
            if ":evidence:" in text:
                return text
            head, _, tail = text.rpartition(":")
            if tail:
                return f"{head}:evidence:{hashlib.sha256(tail.encode('utf-8')).hexdigest()[:12]}"
    return text


@dataclass(frozen=True, slots=True)
class CourseAttempt:
    """One immutable transcript attempt; no student identity is stored."""

    attempt_id: str
    course_id: str
    course_name: str
    credits: Decimal
    earned_credits: Decimal | None = None
    academic_term: str = ""
    repeat_group_id: str | None = None
    identity_status: str = VERIFIED
    course_kind: str = LECTURE
    pool_memberships: tuple[str, ...] = ()
    status: str = PASS
    source_kind: str = "TRANSCRIPT"
    name: str = ""
    term: str = ""
    grade: str = ""
    # Missing posted-grade evidence is unresolved.  Legacy call sites that
    # intentionally exercise a verified repeat rule must opt in explicitly.
    grade_evidence_state: str = UNKNOWN
    # A source-owned effective-attempt/repeat-selection rule may explicitly
    # identify the one winner for a fixed repeat group.  The flag alone is
    # never trusted; it must carry VERIFIED selection evidence.
    effective_attempt: bool = False
    repeat_selection_evidence_state: str = UNKNOWN

    def __post_init__(self):
        course_name = _text(self.course_name) or _text(self.name) or _text(self.course_id)
        course_id = _text(self.course_id) or course_name
        credits = _nonnegative_decimal(self.credits)
        status = _norm_status(self.status)
        earned = _nonnegative_decimal(self.earned_credits, credits if status == PASS else _ZERO)
        earned = min(credits, earned)
        academic_term = _text(self.academic_term) or _text(self.term)
        repeat_group = _text(self.repeat_group_id) or None
        attempt_id = _text(self.attempt_id)
        if not attempt_id:
            attempt_id = f"attempt:{_stable_digest([course_id, course_name, academic_term, str(credits), repeat_group or ''])}"
        object.__setattr__(self, "attempt_id", attempt_id)
        object.__setattr__(self, "course_id", course_id)
        object.__setattr__(self, "course_name", course_name)
        object.__setattr__(self, "name", course_name)
        object.__setattr__(self, "credits", credits)
        object.__setattr__(self, "earned_credits", earned)
        object.__setattr__(self, "academic_term", academic_term)
        object.__setattr__(self, "term", academic_term)
        object.__setattr__(self, "repeat_group_id", repeat_group)
        object.__setattr__(self, "identity_status", _norm_evidence_state(self.identity_status))
        object.__setattr__(self, "course_kind", _norm_course_kind(self.course_kind))
        object.__setattr__(self, "pool_memberships", _tuple_text(self.pool_memberships))
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "source_kind", _text(self.source_kind) or "TRANSCRIPT")
        object.__setattr__(self, "grade", _text(self.grade))
        object.__setattr__(self, "grade_evidence_state", _norm_evidence_state(self.grade_evidence_state))
        object.__setattr__(self, "effective_attempt", bool(self.effective_attempt))
        object.__setattr__(self, "repeat_selection_evidence_state", _norm_evidence_state(self.repeat_selection_evidence_state))

    @property
    def available_credits(self) -> Decimal:
        return self.earned_credits if self.status == PASS else _ZERO


@dataclass(frozen=True, slots=True)
class RequirementSpec:
    """One exact requirement or bounded credit bucket."""

    requirement_id: str
    name: str = ""
    credits_required: Decimal = _ZERO
    max_credits: Decimal | None = None
    eligible_course_ids: tuple[str, ...] = ()
    eligible_pool_ids: tuple[str, ...] = ()
    overflow_routes: tuple[str, ...] = ()
    allowed_course_kinds: tuple[str, ...] = ()
    course_kind: str | None = None
    coverage_state: str = COMPLETE
    evidence_state: str = VERIFIED
    required: bool = True
    repeatable: bool = False
    repeat_policy: str = BEST_ATTEMPT_ONLY
    waiver: bool = False
    eligible_course_names: tuple[str, ...] = ()
    accept_any: bool = False
    bucket: str = ""
    required_credits: Decimal | None = None
    credit_cap: Decimal | None = None
    course_ids: tuple[str, ...] = ()
    pool_ids: tuple[str, ...] = ()
    allowed_kinds: tuple[str, ...] = ()
    coverage: str = ""
    evidence: str = ""
    kind: str = ""
    # Explicit ownership/domain metadata is required when a shared binding
    # projects credit between curricula.  The aliases keep adapters that use
    # ``role`` or ``curriculum_role`` source-compatible.
    owner: str = ""
    domain: str = ""
    role: str = ""
    curriculum_role: str = ""
    requirement_domain: str = ""

    def __post_init__(self):
        requirement_id = _text(self.requirement_id)
        name = _text(self.name) or _text(self.bucket) or requirement_id
        required = _nonnegative_decimal(self.required_credits if self.required_credits is not None else self.credits_required)
        cap_value = self.credit_cap if self.credit_cap is not None else self.max_credits
        cap = _nonnegative_decimal(cap_value, required) if cap_value is not None else required
        cap = max(required, cap)
        course_ids = self.eligible_course_ids or self.course_ids
        pool_ids = self.eligible_pool_ids or self.pool_ids
        allowed_kinds = self.allowed_course_kinds or self.allowed_kinds
        if self.course_kind:
            allowed_kinds = (_norm_course_kind(self.course_kind),)
        normalized_kinds = tuple(_norm_course_kind(item) for item in _tuple_text(allowed_kinds))
        object.__setattr__(self, "requirement_id", requirement_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "credits_required", required)
        object.__setattr__(self, "required_credits", required)
        object.__setattr__(self, "max_credits", cap)
        object.__setattr__(self, "credit_cap", cap)
        object.__setattr__(self, "eligible_course_ids", _tuple_text(course_ids))
        object.__setattr__(self, "course_ids", _tuple_text(course_ids))
        object.__setattr__(self, "eligible_pool_ids", _tuple_text(pool_ids))
        object.__setattr__(self, "pool_ids", _tuple_text(pool_ids))
        object.__setattr__(self, "eligible_course_names", _tuple_text(self.eligible_course_names))
        object.__setattr__(self, "overflow_routes", _tuple_text(self.overflow_routes, preserve_order=True))
        object.__setattr__(self, "allowed_course_kinds", normalized_kinds)
        object.__setattr__(self, "allowed_kinds", normalized_kinds)
        object.__setattr__(self, "course_kind", _norm_course_kind(self.course_kind) if self.course_kind else None)
        object.__setattr__(self, "coverage_state", _norm_coverage(self.coverage or self.coverage_state))
        object.__setattr__(self, "evidence_state", _norm_evidence_state(self.evidence or self.evidence_state))
        object.__setattr__(self, "repeat_policy", _norm_repeat_policy(self.repeat_policy, self.repeatable))
        object.__setattr__(self, "repeatable", self.repeat_policy == REPEATABLE or bool(self.repeatable))
        object.__setattr__(self, "waiver", bool(self.waiver) or _text(self.kind).upper() == WAIVER)
        object.__setattr__(self, "bucket", _text(self.bucket) or requirement_id)
        object.__setattr__(self, "kind", _text(self.kind))
        owner = _text(self.owner or self.role or self.curriculum_role).upper().replace("-", "_").replace(" ", "_")
        domain = _text(self.domain or self.requirement_domain)
        object.__setattr__(self, "owner", owner)
        object.__setattr__(self, "role", owner)
        object.__setattr__(self, "curriculum_role", owner)
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "requirement_domain", domain)


@dataclass(frozen=True, slots=True)
class EquivalencyBinding:
    """An exact, auditable source-attempt to requirement decision."""

    binding_id: str
    source_attempt_id: str
    target_requirement_id: str
    approved_credits: Decimal = _ZERO
    evidence_state: str = VERIFIED
    authority: str = ""
    evidence_reference: str = ""
    direction: str = ""
    shared: bool = False
    source_course_id: str = ""
    target_course_id: str = ""
    source_course_kind: str = ""
    allocation_kind: str = ""
    credits: Decimal | None = None
    decision: str = "APPROVED"
    scope: str = ""
    # Shared credit must name the exact source requirement that owns the
    # exclusive allocation.  Domain/owner hints are optional aliases, but if
    # supplied they must agree with the source/target requirement metadata.
    source_requirement_id: str = ""
    source_domain: str = ""
    target_domain: str = ""
    source_owner: str = ""
    target_owner: str = ""

    def __post_init__(self):
        binding_id = _text(self.binding_id)
        source_id = _text(self.source_attempt_id)
        target_id = _text(self.target_requirement_id)
        direction = _norm_direction(self.direction)
        allocation_kind = _text(self.allocation_kind).upper().replace("-", "_")
        shared = bool(self.shared) or direction in {PRIMARY_TO_TARGET, TARGET_TO_PRIMARY} or allocation_kind in {SHARED_SHADOW, "SHARED_REUSE"}
        if not binding_id:
            binding_id = f"binding:{_stable_digest([source_id, target_id, str(self.approved_credits), direction])}"
        amount = _nonnegative_decimal(self.credits if self.credits is not None else self.approved_credits)
        object.__setattr__(self, "binding_id", binding_id)
        object.__setattr__(self, "source_attempt_id", source_id)
        object.__setattr__(self, "target_requirement_id", target_id)
        object.__setattr__(self, "approved_credits", amount)
        object.__setattr__(self, "credits", amount)
        object.__setattr__(self, "evidence_state", _norm_evidence_state(self.evidence_state))
        object.__setattr__(self, "authority", _text(self.authority))
        object.__setattr__(self, "evidence_reference", _text(self.evidence_reference))
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "shared", shared)
        object.__setattr__(self, "source_course_id", _text(self.source_course_id))
        object.__setattr__(self, "target_course_id", _text(self.target_course_id))
        object.__setattr__(self, "source_course_kind", _norm_course_kind(self.source_course_kind) if self.source_course_kind else "")
        object.__setattr__(self, "allocation_kind", allocation_kind or (SHARED_SHADOW if shared else EXCLUSIVE))
        object.__setattr__(self, "decision", _text(self.decision).upper() or "APPROVED")
        object.__setattr__(self, "scope", _text(self.scope))
        object.__setattr__(self, "source_requirement_id", _text(self.source_requirement_id))
        object.__setattr__(self, "source_domain", _text(self.source_domain))
        object.__setattr__(self, "target_domain", _text(self.target_domain))
        object.__setattr__(self, "source_owner", _text(self.source_owner).upper().replace("-", "_").replace(" ", "_"))
        object.__setattr__(self, "target_owner", _text(self.target_owner).upper().replace("-", "_").replace(" ", "_"))


@dataclass(frozen=True, slots=True)
class WaiverDecision:
    """An explicit, verified student-specific waiver decision.

    ``RequirementSpec.waiver`` only describes that a requirement *may* have a
    waiver path.  It is never itself evidence that the student received one.
    This record is the separate proof required to satisfy that path and does
    not carry any earned credit.
    """

    decision_id: str
    target_requirement_id: str
    evidence_state: str = UNKNOWN
    authority: str = ""
    evidence_reference: str = ""
    decision: str = "APPROVED"

    def __post_init__(self):
        decision_id = _text(self.decision_id)
        target = _text(self.target_requirement_id)
        if not decision_id:
            decision_id = f"waiver:{_stable_digest([target, self.authority, self.evidence_reference])}"
        object.__setattr__(self, "decision_id", decision_id)
        object.__setattr__(self, "target_requirement_id", target)
        object.__setattr__(self, "evidence_state", _norm_evidence_state(self.evidence_state))
        object.__setattr__(self, "authority", _text(self.authority))
        object.__setattr__(self, "evidence_reference", _text(self.evidence_reference))
        object.__setattr__(self, "decision", _text(self.decision).upper() or "APPROVED")


@dataclass(frozen=True, slots=True)
class CreditPortion:
    attempt_id: str
    requirement_id: str
    credits: Decimal
    allocation_kind: str = EXCLUSIVE
    direction: str = ""
    binding_id: str = ""

    def __post_init__(self):
        object.__setattr__(self, "attempt_id", _text(self.attempt_id))
        object.__setattr__(self, "requirement_id", _text(self.requirement_id))
        object.__setattr__(self, "credits", _nonnegative_decimal(self.credits))
        object.__setattr__(self, "allocation_kind", _text(self.allocation_kind).upper() or EXCLUSIVE)
        object.__setattr__(self, "direction", _norm_direction(self.direction))
        object.__setattr__(self, "binding_id", _text(self.binding_id))

    @property
    def kind(self) -> str:
        return self.allocation_kind


@dataclass(frozen=True, slots=True)
class AttemptAllocation:
    attempt_id: str
    source_credits: Decimal
    portions: tuple[CreditPortion, ...] = ()
    unallocated_credits: Decimal = _ZERO

    def __post_init__(self):
        portions = tuple(sorted(self.portions, key=lambda item: (item.requirement_id, item.allocation_kind, item.binding_id)))
        source = _nonnegative_decimal(self.source_credits)
        unallocated = _nonnegative_decimal(self.unallocated_credits)
        object.__setattr__(self, "attempt_id", _text(self.attempt_id))
        object.__setattr__(self, "source_credits", source)
        object.__setattr__(self, "portions", portions)
        object.__setattr__(self, "unallocated_credits", unallocated)


@dataclass(frozen=True, slots=True)
class RequirementResult:
    requirement_id: str
    status: str
    required_credits: Decimal
    exclusive_credits: Decimal
    shared_shadow_credits: Decimal
    effective_credits: Decimal
    deficit: Decimal
    coverage_state: str
    evidence_state: str
    waived: bool = False
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SharedLedger:
    direction: str
    used_credits: Decimal
    limit_credits: Decimal = SHARED_LIMIT
    blocked_credits: Decimal = _ZERO
    binding_ids: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "direction", _norm_direction(self.direction))
        object.__setattr__(self, "used_credits", _nonnegative_decimal(self.used_credits))
        object.__setattr__(self, "limit_credits", _nonnegative_decimal(self.limit_credits, SHARED_LIMIT))
        object.__setattr__(self, "blocked_credits", _nonnegative_decimal(self.blocked_credits))
        object.__setattr__(self, "binding_ids", _tuple_text(self.binding_ids))


@dataclass(frozen=True, slots=True)
class BindingAssessment:
    binding_id: str
    status: str
    reason: str
    direction: str = ""
    approved_credits: Decimal = _ZERO


@dataclass(frozen=True, slots=True)
class WaiverAssessment:
    decision_id: str
    target_requirement_id: str
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class AllocationResult:
    status: str
    allocations: tuple[AttemptAllocation, ...]
    requirement_results: tuple[RequirementResult, ...]
    source_earned_credits: Decimal
    recognized_credits: Decimal
    unallocated_credits: Decimal
    credit_conservation: bool
    shadow_allocations: tuple[CreditPortion, ...] = ()
    shared_ledgers: tuple[SharedLedger, ...] = ()
    binding_assessments: tuple[BindingAssessment, ...] = ()
    waiver_assessments: tuple[WaiverAssessment, ...] = ()
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    search_exhausted: bool = False
    pass_eligible: bool = False
    nodes_searched: int = 0
    objective: tuple[Any, ...] = ()
    # Every distinct best-score assignment is retained as an immutable
    # signature.  A signature is deliberately smaller than a second full
    # result, but still identifies the course-to-requirement routes that make
    # the branch meaningfully different.
    alternative_allocations: tuple[tuple[Any, ...], ...] = ()
    allocation_ambiguous: bool = False

    def __post_init__(self):
        object.__setattr__(self, "status", _text(self.status) or UNKNOWN)
        object.__setattr__(self, "allocations", tuple(self.allocations))
        object.__setattr__(self, "requirement_results", tuple(sorted(self.requirement_results, key=lambda item: item.requirement_id)))
        object.__setattr__(self, "source_earned_credits", _nonnegative_decimal(self.source_earned_credits))
        object.__setattr__(self, "recognized_credits", _nonnegative_decimal(self.recognized_credits))
        object.__setattr__(self, "unallocated_credits", _nonnegative_decimal(self.unallocated_credits))
        object.__setattr__(self, "shadow_allocations", tuple(self.shadow_allocations))
        object.__setattr__(self, "shared_ledgers", tuple(sorted(self.shared_ledgers, key=lambda item: item.direction)))
        object.__setattr__(self, "binding_assessments", tuple(sorted(self.binding_assessments, key=lambda item: item.binding_id)))
        object.__setattr__(self, "waiver_assessments", tuple(sorted(self.waiver_assessments, key=lambda item: item.decision_id)))
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(_safe_diagnostic(item) for item in self.blockers if _text(item))))
        object.__setattr__(self, "warnings", tuple(dict.fromkeys(_safe_diagnostic(item) for item in self.warnings if _text(item))))
        alternatives = tuple(sorted({tuple(item) for item in self.alternative_allocations}, key=repr))
        object.__setattr__(self, "alternative_allocations", alternatives)
        object.__setattr__(self, "allocation_ambiguous", bool(self.allocation_ambiguous))
        object.__setattr__(self, "pass_eligible", bool(self.pass_eligible) and self.status == PASS and not self.search_exhausted)

    @property
    def can_pass(self) -> bool:
        return self.pass_eligible

    @property
    def effective_recognized_credits(self) -> Decimal:
        return self.recognized_credits + sum((item.credits for item in self.shadow_allocations), _ZERO)

    def allocation_for(self, requirement_id: str) -> tuple[CreditPortion, ...]:
        return tuple(
            portion
            for allocation in self.allocations
            for portion in allocation.portions
            if portion.requirement_id == requirement_id
        )

    def requirement_for(self, requirement_id: str) -> RequirementResult | None:
        return next((item for item in self.requirement_results if item.requirement_id == requirement_id), None)

    def shared_ledger(self, direction: str) -> SharedLedger | None:
        normalized = _norm_direction(direction)
        return next((item for item in self.shared_ledgers if item.direction == normalized), None)

    @property
    def alternatives(self) -> tuple[tuple[Any, ...], ...]:
        """Compatibility/readability alias for the best-route signatures."""

        return self.alternative_allocations


def _as_attempt(value: Any) -> CourseAttempt | None:
    if isinstance(value, CourseAttempt):
        return value
    if not isinstance(value, Mapping):
        return None
    return CourseAttempt(
        attempt_id=_text(value.get("attempt_id") or value.get("id")),
        course_id=_text(value.get("course_id") or value.get("course_code") or value.get("code") or value.get("name")),
        course_name=_text(value.get("course_name") or value.get("name") or value.get("title")),
        credits=value.get("credits", value.get("credit", value.get("total_credit", 0))),
        earned_credits=value.get("earned_credits", value.get("completed_credit")),
        academic_term=value.get("academic_term", value.get("term", value.get("semester", ""))),
        repeat_group_id=value.get("repeat_group_id", value.get("repeat_group")),
        # A plain mapping is an untrusted boundary object.  Callers must
        # carry an explicit identity decision before a direct match may pass.
        identity_status=value.get("identity_status", value.get("course_identity_status", UNKNOWN)),
        course_kind=value.get("course_kind", value.get("component_type", value.get("kind", UNKNOWN))),
        pool_memberships=value.get("pool_memberships", value.get("pool_membership", value.get("pools", value.get("eligible_pools", ())))),
        status=value.get("status", PASS if value.get("is_completed", True) else "IN_PROGRESS"),
        source_kind=value.get("source_kind", "TRANSCRIPT"),
        grade=value.get("grade", ""),
        grade_evidence_state=value.get("grade_evidence_state", value.get("grade_trust", UNKNOWN)),
        effective_attempt=value.get("effective_attempt", value.get("is_effective_attempt", False)),
        repeat_selection_evidence_state=value.get(
            "repeat_selection_evidence_state",
            value.get("effective_attempt_evidence_state", value.get("repeat_selection_state", UNKNOWN)),
        ),
    )


def _as_requirement(value: Any) -> RequirementSpec | None:
    if isinstance(value, RequirementSpec):
        return value
    if not isinstance(value, Mapping):
        return None
    return RequirementSpec(
        requirement_id=value.get("requirement_id", value.get("id", value.get("key", ""))),
        name=value.get("name", value.get("label", value.get("title", ""))),
        credits_required=value.get("credits_required", value.get("required_credits", value.get("credits", value.get("credit", 0)))),
        max_credits=value.get("max_credits", value.get("credit_cap")),
        eligible_course_ids=value.get("eligible_course_ids", value.get("course_ids", value.get("course_id", ()))),
        eligible_pool_ids=value.get("eligible_pool_ids", value.get("pool_ids", value.get("pool_id", ()))),
        eligible_course_names=value.get("eligible_course_names", value.get("course_names", ())),
        overflow_routes=value.get("overflow_routes", value.get("overflow", ())),
        allowed_course_kinds=value.get("allowed_course_kinds", value.get("allowed_kinds", ())),
        course_kind=value.get("course_kind"),
        # A mapping has no provenance by itself.  Keep it fail-closed unless
        # the caller explicitly supplies both coverage and evidence state.
        coverage_state=value.get("coverage_state", value.get("coverage", NONE)),
        evidence_state=value.get("evidence_state", value.get("evidence", UNKNOWN)),
        required=value.get("required", True),
        repeatable=value.get("repeatable", value.get("repeatable_attempts", False)),
        repeat_policy=value.get("repeat_policy", BEST_ATTEMPT_ONLY),
        waiver=value.get("waiver", False),
        accept_any=value.get("accept_any", False),
        bucket=value.get("bucket", ""),
        kind=value.get("kind", ""),
        owner=value.get("owner", value.get("role", value.get("curriculum_role", ""))),
        domain=value.get("domain", value.get("requirement_domain", "")),
    )


def _as_binding(value: Any) -> EquivalencyBinding | None:
    if isinstance(value, EquivalencyBinding):
        return value
    if not isinstance(value, Mapping):
        return None
    return EquivalencyBinding(
        binding_id=value.get("binding_id", value.get("id", value.get("record_id", ""))),
        source_attempt_id=value.get("source_attempt_id", value.get("source_id", value.get("attempt_id", ""))),
        target_requirement_id=value.get("target_requirement_id", value.get("requirement_id", value.get("target_id", ""))),
        approved_credits=value.get("approved_credits", value.get("credits", value.get("credit", 0))),
        evidence_state=value.get("evidence_state", value.get("status", UNKNOWN)),
        authority=value.get("authority", ""),
        evidence_reference=value.get("evidence_reference", value.get("source_reference", value.get("evidence_id", ""))),
        direction=value.get("direction", value.get("ledger", "")),
        shared=value.get("shared", False),
        source_course_id=value.get("source_course_id", value.get("source_course_code", "")),
        target_course_id=value.get("target_course_id", value.get("target_course_code", "")),
        source_course_kind=value.get("source_course_kind", value.get("course_kind", "")),
        allocation_kind=value.get("allocation_kind", value.get("kind", "")),
        decision=value.get("decision", "APPROVED"),
        scope=value.get("scope", ""),
        source_requirement_id=value.get("source_requirement_id", value.get("source_requirement", "")),
        source_domain=value.get("source_domain", ""),
        target_domain=value.get("target_domain", ""),
        source_owner=value.get("source_owner", ""),
        target_owner=value.get("target_owner", ""),
    )


def _attempt_quality(attempt: CourseAttempt) -> tuple[Any, ...]:
    status_rank = {PASS: 4, "IN_PROGRESS": 3, WAIVER: 2, UNKNOWN: 1, FAIL: 0}.get(attempt.status, 0)
    return (
        status_rank,
        attempt.available_credits,
        attempt.earned_credits,
        attempt.credits,
        attempt.academic_term,
        attempt.course_id,
        attempt.course_name,
        attempt.attempt_id,
    )


def _normalize_attempts(
    values: Any,
    *,
    with_issues: bool = False,
) -> tuple[CourseAttempt, ...] | tuple[tuple[CourseAttempt, ...], tuple[str, ...]]:
    if values is None or isinstance(values, (str, bytes)):
        values = (values,) if values is not None else ()
    elif isinstance(values, Mapping):
        values = (values,)
    attempts = [item for value in values or () if (item := _as_attempt(value)) is not None]
    grouped: dict[str, list[CourseAttempt]] = {}
    for item in attempts:
        grouped.setdefault(item.attempt_id, []).append(item)
    issues: list[str] = []
    selected: list[CourseAttempt] = []
    for attempt_id, items in grouped.items():
        fingerprints = {_input_fingerprint(item) for item in items}
        if len(fingerprints) > 1:
            # Retain a deterministic representative for inspection, but do
            # not silently choose between conflicting records.
            issues.append(f"DUPLICATE_ATTEMPT_ID:{attempt_id}")
        selected.append(max(items, key=_attempt_quality))
    normalized = tuple(sorted(selected, key=lambda item: (item.attempt_id, item.course_id, item.academic_term)))
    return (normalized, tuple(sorted(set(issues)))) if with_issues else normalized


def _input_values(values: Any) -> tuple[Any, ...]:
    if values is None or isinstance(values, (str, bytes)):
        return (values,) if values is not None else ()
    if isinstance(values, Mapping):
        return (values,)
    return tuple(values or ()) if isinstance(values, Sequence | set) else (values,)


def _canonical_input(value: Any) -> Any:
    """Canonicalize all fields for duplicate/conflict detection in memory."""

    if isinstance(value, Mapping):
        return {str(key): _canonical_input(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical_input(item) for item in value]
    if isinstance(value, set):
        return sorted((_canonical_input(item) for item in value), key=repr)
    if isinstance(value, (bytes, bytearray)):
        # Keep only a digest, never the raw bytes, even in diagnostics.
        return {"bytes_sha256": hashlib.sha256(bytes(value)).hexdigest()}
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        return {item.name: _canonical_input(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _input_fingerprint(value: Any) -> str:
    return _stable_digest(_canonical_input(value))


def _normalize_requirements(
    values: Any,
    *,
    with_issues: bool = False,
) -> tuple[RequirementSpec, ...] | tuple[tuple[RequirementSpec, ...], tuple[str, ...]]:
    if values is None or isinstance(values, (str, bytes)):
        values = (values,) if values is not None else ()
    elif isinstance(values, Mapping):
        values = (values,)
    entries: dict[str, list[tuple[RequirementSpec, str]]] = {}
    for value in values or ():
        item = _as_requirement(value)
        if item is not None and item.requirement_id:
            entries.setdefault(item.requirement_id, []).append((item, _input_fingerprint(value)))
    issues: list[str] = []
    unique: dict[str, RequirementSpec] = {}
    for requirement_id, candidates in entries.items():
        fingerprints = {fingerprint for _item, fingerprint in candidates}
        if len(candidates) > 1 and len(fingerprints) > 1:
            issues.append(f"DUPLICATE_REQUIREMENT_ID:{requirement_id}")
        # Pick a stable representative even for conflicting input order.
        unique[requirement_id] = min(candidates, key=lambda pair: pair[1])[0]
    normalized = tuple(sorted(unique.values(), key=lambda item: item.requirement_id))
    return (normalized, tuple(sorted(set(issues)))) if with_issues else normalized


def _normalize_bindings(
    values: Any,
    *,
    with_issues: bool = False,
) -> tuple[EquivalencyBinding, ...] | tuple[tuple[EquivalencyBinding, ...], tuple[str, ...]]:
    if values is None or isinstance(values, (str, bytes)):
        values = (values,) if values is not None else ()
    elif isinstance(values, Mapping):
        values = (values,)
    entries: dict[str, list[tuple[EquivalencyBinding, str]]] = {}
    for value in values or ():
        item = _as_binding(value)
        if item is not None and item.binding_id:
            entries.setdefault(item.binding_id, []).append((item, _input_fingerprint(value)))
    issues: list[str] = []
    unique: dict[str, EquivalencyBinding] = {}
    for binding_id, candidates in entries.items():
        fingerprints = {fingerprint for _item, fingerprint in candidates}
        if len(candidates) > 1 and len(fingerprints) > 1:
            issues.append(f"DUPLICATE_BINDING_ID:{binding_id}")
        unique[binding_id] = min(candidates, key=lambda pair: pair[1])[0]
    normalized = tuple(sorted(unique.values(), key=lambda item: item.binding_id))
    return (normalized, tuple(sorted(set(issues)))) if with_issues else normalized


def _as_waiver_decision(value: Any) -> WaiverDecision | None:
    if isinstance(value, WaiverDecision):
        return value
    if not isinstance(value, Mapping):
        return None
    return WaiverDecision(
        decision_id=value.get("decision_id", value.get("id", value.get("evidence_id", ""))),
        target_requirement_id=value.get("target_requirement_id", value.get("requirement_id", value.get("target_id", ""))),
        evidence_state=value.get("evidence_state", value.get("status", UNKNOWN)),
        authority=value.get("authority", ""),
        evidence_reference=value.get("evidence_reference", value.get("source_reference", value.get("evidence_id", ""))),
        decision=value.get("decision", "APPROVED"),
    )


def _normalize_waiver_decisions(
    values: Any,
    *,
    with_issues: bool = False,
) -> tuple[WaiverDecision, ...] | tuple[tuple[WaiverDecision, ...], tuple[str, ...]]:
    entries: dict[str, list[tuple[WaiverDecision, str]]] = {}
    for value in _input_values(values):
        item = _as_waiver_decision(value)
        if item is not None and item.decision_id:
            entries.setdefault(item.decision_id, []).append((item, _input_fingerprint(value)))
    unique: dict[str, WaiverDecision] = {}
    issues: list[str] = []
    for decision_id, candidates in entries.items():
        fingerprints = {fingerprint for _item, fingerprint in candidates}
        if len(fingerprints) > 1:
            issues.append(f"DUPLICATE_WAIVER_DECISION_ID:{decision_id}")
        unique[decision_id] = min(candidates, key=lambda pair: pair[1])[0]
    normalized = tuple(sorted(unique.values(), key=lambda item: item.decision_id))
    return (normalized, tuple(sorted(set(issues)))) if with_issues else normalized


def _validate_waiver_decisions(
    decisions: tuple[WaiverDecision, ...],
    requirements: tuple[RequirementSpec, ...],
) -> tuple[set[str], tuple[WaiverAssessment, ...], set[str], list[str]]:
    """Return approved waiver targets plus deterministic audit assessments."""

    requirements_by_id = {item.requirement_id: item for item in requirements}
    approved_targets: set[str] = set()
    unknown_targets: set[str] = set()
    assessments: list[WaiverAssessment] = []
    warnings: list[str] = []
    target_decisions: dict[str, list[WaiverDecision]] = {}
    for decision in decisions:
        target_decisions.setdefault(decision.target_requirement_id, []).append(decision)
    for decision in decisions:
        requirement = requirements_by_id.get(decision.target_requirement_id)
        valid = bool(requirement and requirement.waiver)
        reason = ""
        if requirement is None:
            reason = "waiver target requirement is missing"
        elif not requirement.waiver:
            reason = "target requirement has no waiver path"
        elif decision.evidence_state != VERIFIED or decision.decision != "APPROVED":
            valid = False
            reason = "waiver evidence is not VERIFIED/APPROVED"
        elif not decision.authority or not decision.evidence_reference:
            valid = False
            reason = "waiver authority or evidence reference is missing"
        elif len(target_decisions.get(decision.target_requirement_id, ())) > 1:
            valid = False
            reason = "multiple waiver decisions target the same requirement"
        if valid:
            approved_targets.add(decision.target_requirement_id)
            assessments.append(WaiverAssessment(decision.decision_id, decision.target_requirement_id, PASS, "verified approved waiver decision"))
        else:
            if decision.target_requirement_id:
                unknown_targets.add(decision.target_requirement_id)
            assessments.append(WaiverAssessment(decision.decision_id, decision.target_requirement_id, UNKNOWN, reason or "waiver decision is unresolved"))
            warnings.append(f"UNVERIFIED_WAIVER:{decision.decision_id}")
    for requirement in requirements:
        if requirement.waiver and requirement.requirement_id not in approved_targets:
            unknown_targets.add(requirement.requirement_id)
    return approved_targets, tuple(assessments), unknown_targets, warnings


def _course_kind_allowed(attempt: CourseAttempt, requirement: RequirementSpec) -> bool | None:
    allowed = requirement.allowed_course_kinds
    if requirement.course_kind == LAB or LAB in allowed:
        return attempt.course_kind == LAB
    if allowed and attempt.course_kind not in allowed:
        return False
    if attempt.course_kind not in {LECTURE, COMBINED, LAB}:
        return None
    return True


def _direct_match(attempt: CourseAttempt, requirement: RequirementSpec) -> bool | None:
    kind = _course_kind_allowed(attempt, requirement)
    if kind is False:
        return False
    if kind is None:
        return None
    formal_exact = (
        attempt.course_id in requirement.eligible_course_ids
        or bool(set(attempt.pool_memberships).intersection(requirement.eligible_pool_ids))
        or requirement.accept_any
    )
    # Keep same-name rows visible as planning candidates, but never let title
    # equality establish a formal identity or consume graduation credit.
    if not formal_exact:
        return None if attempt.course_name in requirement.eligible_course_names else False
    if attempt.identity_status != VERIFIED:
        return None
    return True


def _binding_is_verified(binding: EquivalencyBinding, attempt: CourseAttempt, requirement: RequirementSpec) -> tuple[bool, str]:
    if not binding.binding_id or not binding.source_attempt_id or not binding.target_requirement_id:
        return False, "binding identity is incomplete"
    if binding.evidence_state != VERIFIED or binding.decision != "APPROVED":
        return False, "equivalency evidence is not VERIFIED/APPROVED"
    if not binding.authority or not binding.evidence_reference:
        return False, "equivalency authority or evidence reference is missing"
    if binding.source_attempt_id != attempt.attempt_id or binding.target_requirement_id != requirement.requirement_id:
        return False, "source attempt or target requirement does not match"
    if binding.source_course_id and binding.source_course_id != attempt.course_id:
        return False, "source course identity does not match"
    if binding.target_course_id and requirement.eligible_course_ids and binding.target_course_id not in requirement.eligible_course_ids:
        return False, "target course identity does not match"
    if binding.source_course_kind and binding.source_course_kind != attempt.course_kind:
        return False, "source course component kind does not match"
    kind = _course_kind_allowed(attempt, requirement)
    if kind is not True:
        return False, "lecture/combined attempt cannot satisfy LAB requirement"
    if binding.approved_credits <= _ZERO:
        return False, "approved equivalency credits are zero"
    return True, ""


def _norm_owner(value: Any) -> str:
    text = _text(value).upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "PRIMARY": "PRIMARY",
        "HOME": "PRIMARY",
        "MAJOR": "PRIMARY",
        "SOURCE": "PRIMARY",
        "主修": "PRIMARY",
        "TARGET": "TARGET",
        "SECONDARY": "TARGET",
        "DOUBLE_MAJOR": "TARGET",
        "DOUBLEMAJOR": "TARGET",
        "雙主修": "TARGET",
    }
    return aliases.get(text, text)


def _shared_binding_scope(
    binding: EquivalencyBinding,
    attempt: CourseAttempt | None,
    source_requirement: RequirementSpec | None,
    target_requirement: RequirementSpec | None,
    exclusive_by_attempt_requirement: Mapping[tuple[str, str], Decimal],
) -> tuple[bool, str]:
    """Validate source ownership before a shared shadow is projected."""

    if attempt is None or source_requirement is None or target_requirement is None:
        return False, "shared source/target requirement is missing"
    if not binding.source_requirement_id:
        return False, "shared binding source requirement scope is missing"
    if source_requirement.requirement_id == target_requirement.requirement_id:
        return False, "shared binding cannot target its source requirement"
    if not binding.direction:
        return False, "shared binding direction is missing"
    source_owner = _norm_owner(source_requirement.owner or source_requirement.role or source_requirement.curriculum_role)
    target_owner = _norm_owner(target_requirement.owner or target_requirement.role or target_requirement.curriculum_role)
    expected = (
        ("PRIMARY", "TARGET")
        if binding.direction == PRIMARY_TO_TARGET
        else ("TARGET", "PRIMARY")
        if binding.direction == TARGET_TO_PRIMARY
        else None
    )
    if expected is None:
        return False, "shared binding direction is unsupported"
    if (source_owner, target_owner) != expected:
        return False, "shared binding ownership does not match direction"
    if not binding.source_owner or not binding.target_owner or not binding.source_domain or not binding.target_domain:
        return False, "shared binding owner/domain scope is incomplete"
    if _norm_owner(binding.source_owner) != source_owner:
        return False, "shared binding source owner does not match requirement"
    if _norm_owner(binding.target_owner) != target_owner:
        return False, "shared binding target owner does not match requirement"
    source_domain = _text(source_requirement.domain or source_requirement.requirement_domain)
    target_domain = _text(target_requirement.domain or target_requirement.requirement_domain)
    if not source_domain or not target_domain:
        return False, "shared requirement ownership/domain metadata is incomplete"
    if binding.source_domain != source_domain:
        return False, "shared binding source domain does not match requirement"
    if binding.target_domain != target_domain:
        return False, "shared binding target domain does not match requirement"
    if exclusive_by_attempt_requirement.get((attempt.attempt_id, source_requirement.requirement_id), _ZERO) <= _ZERO:
        return False, "shared source requirement has no positive exclusive allocation"
    return True, ""


def _repeat_filter(attempts: tuple[CourseAttempt, ...], requirements: tuple[RequirementSpec, ...]) -> tuple[CourseAttempt, ...]:
    """Return deduplicated attempts without choosing a repeat winner early.

    Repeat policy is a property of the *route* an attempt takes, not merely a
    property of the input requirement set.  Filtering a whole repeat group
    up-front loses legal repeatable-only allocations and, conversely, keeping
    every attempt without a route guard lets one group straddle fixed and
    repeatable requirements.  The search therefore keeps all distinct
    attempts and enforces the group mode while visiting each route; the final
    result projects only the legally active attempts.

    ``_normalize_attempts`` has already collapsed duplicate parser rows, so
    this function is intentionally a stable no-op kept as a named boundary
    for callers/tests that relied on the old helper.
    """

    del requirements
    return tuple(sorted(attempts, key=lambda item: (item.attempt_id, item.course_id, item.academic_term)))


def _option_portions(
    attempt: CourseAttempt,
    requirement: RequirementSpec,
    requirements_by_id: Mapping[str, RequirementSpec],
    amounts: Mapping[str, Decimal],
    binding: EquivalencyBinding | None = None,
) -> tuple[tuple[CreditPortion, ...], Decimal] | None:
    available = attempt.available_credits
    if attempt.status == WAIVER:
        return (CreditPortion(attempt.attempt_id, requirement.requirement_id, _ZERO, WAIVER),), _ZERO
    if available <= _ZERO:
        return None
    current = amounts.get(requirement.requirement_id, _ZERO)
    capacity = max(_ZERO, requirement.max_credits - current)
    if capacity <= _ZERO:
        return None
    binding_cap = binding.approved_credits if binding is not None else available
    if binding is not None and binding_cap <= _ZERO:
        return None
    amount = min(available, capacity, binding_cap)
    portions = [
        CreditPortion(
            attempt.attempt_id,
            requirement.requirement_id,
            amount,
            EXCLUSIVE,
            binding_id=binding.binding_id if binding is not None else "",
        )
    ]
    residual = available - amount
    if residual > _ZERO:
        for route_id in requirement.overflow_routes:
            route = requirements_by_id.get(route_id)
            if route is None:
                continue
            if _course_kind_allowed(attempt, route) is not True:
                continue
            route_capacity = max(_ZERO, route.max_credits - amounts.get(route.requirement_id, _ZERO) - sum((item.credits for item in portions if item.requirement_id == route.requirement_id), _ZERO))
            if route_capacity <= _ZERO:
                continue
            route_amount = min(residual, route_capacity)
            if route_amount > _ZERO:
                portions.append(CreditPortion(attempt.attempt_id, route.requirement_id, route_amount, EXCLUSIVE))
                residual -= route_amount
            if residual <= _ZERO:
                break
    return tuple(portions), residual


def _apply_portions(amounts: Mapping[str, Decimal], portions: Sequence[CreditPortion]) -> dict[str, Decimal]:
    updated = dict(amounts)
    for portion in portions:
        if portion.allocation_kind != EXCLUSIVE:
            continue
        updated[portion.requirement_id] = updated.get(portion.requirement_id, _ZERO) + portion.credits
    return updated


def _signature(choices: Sequence[AttemptAllocation]) -> tuple[Any, ...]:
    return tuple(
        (
            choice.attempt_id,
            tuple(
                (
                    portion.requirement_id,
                    str(portion.credits),
                    portion.allocation_kind,
                    portion.direction,
                )
                for portion in choice.portions
            ),
            str(choice.unallocated_credits),
        )
        for choice in choices
    )


def _positive_portions(
    portions: Sequence[CreditPortion],
) -> tuple[CreditPortion, ...]:
    return tuple(item for item in portions if item.allocation_kind == EXCLUSIVE and item.credits > _ZERO)


def _repeat_mode_for_portions(
    portions: Sequence[CreditPortion],
    requirements_by_id: Mapping[str, RequirementSpec],
) -> str | None:
    """Return the repeat mode represented by a positive route.

    An option can contain an explicit overflow route.  If any part of that
    route lands in a fixed requirement, the whole option is fixed for repeat
    accounting; this prevents a single attempt from straddling fixed and
    repeatable requirements through an overflow edge.
    """

    positive = _positive_portions(portions)
    if not positive:
        return None
    modes = {
        requirement.repeat_policy
        for item in positive
        if (requirement := requirements_by_id.get(item.requirement_id)) is not None
    }
    if BEST_ATTEMPT_ONLY in modes and REPEATABLE in modes:
        # One retake route may not straddle fixed and repeatable policy
        # classes through an overflow edge.
        return "MIXED"
    if BEST_ATTEMPT_ONLY in modes:
        return BEST_ATTEMPT_ONLY
    return REPEATABLE


def _repeat_option_allowed(
    attempt: CourseAttempt,
    portions: Sequence[CreditPortion],
    requirements_by_id: Mapping[str, RequirementSpec],
    repeat_states: Mapping[str, tuple[str, str | None]],
    *,
    repeat_selection_winners: Mapping[str, str] | None = None,
    repeat_selection_unknown_groups: set[str] | None = None,
) -> bool:
    group_id = attempt.repeat_group_id
    mode = _repeat_mode_for_portions(portions, requirements_by_id)
    if mode == "MIXED":
        return False
    if not group_id or mode is None:
        return True
    repeat_selection_winners = repeat_selection_winners or {}
    repeat_selection_unknown_groups = repeat_selection_unknown_groups or set()
    if mode == BEST_ATTEMPT_ONLY:
        if group_id in repeat_selection_unknown_groups:
            return False
        selected_winner = repeat_selection_winners.get(group_id)
        if selected_winner is not None and selected_winner != attempt.attempt_id:
            return False
    previous = repeat_states.get(group_id)
    if previous is None:
        return True
    previous_mode, previous_attempt_id = previous
    if mode == REPEATABLE:
        # Once a group has contributed to a fixed requirement, another
        # attempt in that group cannot be counted by a repeatable bucket.
        return previous_mode == REPEATABLE
    # BEST_ATTEMPT_ONLY allows one and only one source attempt for the group.
    return previous_mode == BEST_ATTEMPT_ONLY and previous_attempt_id == attempt.attempt_id


def _repeat_evidence_unknown(
    attempts: tuple[CourseAttempt, ...],
    choices: Sequence[AttemptAllocation],
    requirements_by_id: Mapping[str, RequirementSpec],
) -> set[str]:
    """Return fixed-repeat requirements whose selected winner lacks evidence.

    Numeric credits alone are not enough to choose a legally effective repeat
    winner.  The production adapter records the posted grade evidence state;
    a missing/unverified state therefore makes every affected requirement
    unresolved without inventing a grade conversion.
    """

    attempts_by_id = {item.attempt_id: item for item in attempts}
    unknown: set[str] = set()
    for choice in choices:
        attempt = attempts_by_id.get(choice.attempt_id)
        if attempt is None or not attempt.repeat_group_id:
            continue
        if _repeat_mode_for_portions(choice.portions, requirements_by_id) != BEST_ATTEMPT_ONLY:
            continue
        if attempt.grade_evidence_state == VERIFIED or (
            attempt.effective_attempt and attempt.repeat_selection_evidence_state == VERIFIED
        ):
            continue
        unknown.update(
            portion.requirement_id
            for portion in _positive_portions(choice.portions)
        )
    return unknown


def _repeat_selection_state(
    attempts: tuple[CourseAttempt, ...],
    requirements: tuple[RequirementSpec, ...],
) -> tuple[dict[str, str], set[str]]:
    """Resolve explicit fixed-repeat winners without ordering heuristics.

    Returns ``(winner_by_group, unresolved_groups)``.  A group with multiple
    positive attempts is unresolved unless exactly one attempt is explicitly
    marked effective with VERIFIED selection evidence.  Repeatable-only
    requirements do not need a winner and are intentionally ignored here.
    """

    if not any(item.repeat_policy == BEST_ATTEMPT_ONLY for item in requirements):
        return {}, set()
    grouped: dict[str, list[CourseAttempt]] = {}
    for item in attempts:
        if item.repeat_group_id and item.available_credits > _ZERO:
            grouped.setdefault(item.repeat_group_id, []).append(item)
    winners: dict[str, str] = {}
    unresolved: set[str] = set()
    for group_id, items in grouped.items():
        if len(items) <= 1:
            continue
        explicit = [
            item
            for item in items
            if item.effective_attempt and item.repeat_selection_evidence_state == VERIFIED
        ]
        if len(explicit) == 1:
            winners[group_id] = explicit[0].attempt_id
        else:
            unresolved.add(group_id)
    return winners, unresolved


def _active_attempt_ids(
    attempts: tuple[CourseAttempt, ...],
    choices: Sequence[AttemptAllocation],
    requirements_by_id: Mapping[str, RequirementSpec],
    *,
    repeat_selection_winners: Mapping[str, str] | None = None,
    repeat_selection_unknown_groups: set[str] | None = None,
) -> set[str]:
    """Determine which attempts contribute legally earned source credit.

    A fixed repeat group contributes the one attempt that was actually routed
    to a fixed requirement.  A repeatable-only group may contribute every
    attempt.  A group with no selected route falls back to its deterministic
    best attempt, matching the usual best-attempt transcript rule.
    """

    attempts_by_group: dict[str, list[CourseAttempt]] = {}
    active: set[str] = set()
    for attempt in attempts:
        if attempt.repeat_group_id:
            attempts_by_group.setdefault(attempt.repeat_group_id, []).append(attempt)
        else:
            active.add(attempt.attempt_id)

    selected_by_group: dict[str, list[tuple[str, str]]] = {}
    for choice in choices:
        attempt = next((item for item in attempts if item.attempt_id == choice.attempt_id), None)
        if attempt is None or not attempt.repeat_group_id:
            continue
        mode = _repeat_mode_for_portions(choice.portions, requirements_by_id)
        if mode is not None:
            selected_by_group.setdefault(attempt.repeat_group_id, []).append((mode, attempt.attempt_id))

    repeat_selection_winners = repeat_selection_winners or {}
    repeat_selection_unknown_groups = repeat_selection_unknown_groups or set()
    for group_id, grouped_attempts in attempts_by_group.items():
        selected = selected_by_group.get(group_id, [])
        if any(mode == BEST_ATTEMPT_ONLY for mode, _attempt_id in selected):
            # The DFS guard ensures this set contains at most one ID.  Keep a
            # deterministic fallback in case a caller constructs a result by
            # hand or a future route violates that invariant.
            fixed_ids = sorted({attempt_id for mode, attempt_id in selected if mode == BEST_ATTEMPT_ONLY})
            active.add(fixed_ids[0] if fixed_ids else max(grouped_attempts, key=_attempt_quality).attempt_id)
        elif any(mode == REPEATABLE for mode, _attempt_id in selected):
            active.update(item.attempt_id for item in grouped_attempts)
        elif group_id in repeat_selection_unknown_groups:
            # Keep every released attempt in the conservation ledger while
            # the fixed-repeat route itself remains unresolved.  No winner is
            # silently selected merely to make the totals look consistent.
            active.update(item.attempt_id for item in grouped_attempts)
        elif group_id in repeat_selection_winners:
            active.add(repeat_selection_winners[group_id])
        else:
            active.add(max(grouped_attempts, key=_attempt_quality).attempt_id)
    return active


def _legalize_choices(
    attempts: tuple[CourseAttempt, ...],
    choices: Sequence[AttemptAllocation],
    requirements_by_id: Mapping[str, RequirementSpec],
    *,
    repeat_selection_winners: Mapping[str, str] | None = None,
    repeat_selection_unknown_groups: set[str] | None = None,
) -> tuple[AttemptAllocation, ...]:
    active_ids = _active_attempt_ids(
        attempts,
        choices,
        requirements_by_id,
        repeat_selection_winners=repeat_selection_winners,
        repeat_selection_unknown_groups=repeat_selection_unknown_groups,
    )
    attempts_by_id = {item.attempt_id: item for item in attempts}
    legalized: list[AttemptAllocation] = []
    for choice in choices:
        if choice.attempt_id not in active_ids:
            continue
        source = attempts_by_id[choice.attempt_id].available_credits
        used = sum((item.credits for item in choice.portions if item.allocation_kind == EXCLUSIVE), _ZERO)
        legalized.append(AttemptAllocation(choice.attempt_id, source, choice.portions, max(_ZERO, source - used)))
    return tuple(legalized)


def _shared_projection(
    attempts: tuple[CourseAttempt, ...],
    requirements: tuple[RequirementSpec, ...],
    bindings: tuple[EquivalencyBinding, ...],
    exclusive_amounts: Mapping[str, Decimal],
    exclusive_allocations: Sequence[AttemptAllocation] = (),
) -> tuple[tuple[CreditPortion, ...], tuple[SharedLedger, ...], tuple[BindingAssessment, ...], set[str], list[str]]:
    attempts_by_id = {item.attempt_id: item for item in attempts}
    requirements_by_id = {item.requirement_id: item for item in requirements}
    exclusive_by_attempt: dict[str, Decimal] = {}
    exclusive_by_attempt_requirement: dict[tuple[str, str], Decimal] = {}
    for allocation in exclusive_allocations:
        amount = _ZERO
        for portion in allocation.portions:
            if portion.allocation_kind != EXCLUSIVE or portion.credits <= _ZERO:
                continue
            amount += portion.credits
            key = (allocation.attempt_id, portion.requirement_id)
            exclusive_by_attempt_requirement[key] = exclusive_by_attempt_requirement.get(key, _ZERO) + portion.credits
        if amount > _ZERO:
            exclusive_by_attempt[allocation.attempt_id] = exclusive_by_attempt.get(allocation.attempt_id, _ZERO) + amount
    shared_by_attempt: dict[str, Decimal] = {}
    ledgers: dict[str, Decimal] = {PRIMARY_TO_TARGET: _ZERO, TARGET_TO_PRIMARY: _ZERO}
    ledger_binding_ids: dict[str, list[str]] = {PRIMARY_TO_TARGET: [], TARGET_TO_PRIMARY: []}
    blocked: dict[str, Decimal] = {PRIMARY_TO_TARGET: _ZERO, TARGET_TO_PRIMARY: _ZERO}
    shadows: list[CreditPortion] = []
    assessments: list[BindingAssessment] = []
    unknown_requirements: set[str] = set()
    warnings: list[str] = []
    for binding in bindings:
        if not binding.shared:
            # Exclusive bindings were already validated while constructing the
            # ordinary candidate set; they do not consume a shared ledger.
            continue
        attempt = attempts_by_id.get(binding.source_attempt_id)
        requirement = requirements_by_id.get(binding.target_requirement_id)
        direction = binding.direction or (PRIMARY_TO_TARGET if binding.shared else "")
        valid = bool(attempt and requirement and direction in {PRIMARY_TO_TARGET, TARGET_TO_PRIMARY})
        reason = ""
        if not valid:
            reason = "binding source/target/direction is not resolvable"
        elif binding.evidence_state != VERIFIED or binding.decision != "APPROVED":
            valid = False
            reason = "equivalency evidence is not VERIFIED/APPROVED"
        elif not binding.authority or not binding.evidence_reference:
            valid = False
            reason = "equivalency authority or evidence reference is missing"
        elif binding.approved_credits <= _ZERO:
            valid = False
            reason = "approved equivalency credits are zero"
        elif attempt is None or requirement is None:
            valid = False
            reason = "binding source attempt or target requirement is missing"
        else:
            valid, reason = _binding_is_verified(binding, attempt, requirement)
        if not valid:
            assessments.append(BindingAssessment(binding.binding_id, UNKNOWN, reason, direction, binding.approved_credits))
            if requirement is not None:
                unknown_requirements.add(requirement.requirement_id)
            warnings.append(f"UNVERIFIED_EQUIVALENCY:{binding.binding_id}")
            continue
        source_requirement = requirements_by_id.get(binding.source_requirement_id)
        scoped, scope_reason = _shared_binding_scope(
            binding,
            attempt,
            source_requirement,
            requirement,
            exclusive_by_attempt_requirement,
        )
        if not scoped:
            assessments.append(BindingAssessment(binding.binding_id, UNKNOWN, scope_reason, direction, binding.approved_credits))
            if requirement is not None:
                unknown_requirements.add(requirement.requirement_id)
            warnings.append(f"SHARED_SCOPE_UNKNOWN:{binding.binding_id}")
            if "no positive exclusive allocation" in scope_reason:
                # Retain the specific source-cap diagnostic for callers that
                # relied on the earlier shared-source warning.
                warnings.append(f"SHARED_SOURCE_USE_UNKNOWN:{binding.binding_id}")
            continue
        remaining_ledger = max(_ZERO, SHARED_LIMIT - ledgers[direction])
        # Shared credit is a shadow of a real exclusive allocation.  It may
        # never be minted from an otherwise unallocated transcript attempt,
        # and multiple mappings must share the same source capacity.
        source_exclusive = exclusive_by_attempt.get(attempt.attempt_id, _ZERO)
        source_remaining = max(_ZERO, source_exclusive - shared_by_attempt.get(attempt.attempt_id, _ZERO))
        if source_remaining <= _ZERO:
            assessments.append(
                BindingAssessment(
                    binding.binding_id,
                    UNKNOWN,
                    "shared source attempt has no positive exclusive allocation",
                    direction,
                    binding.approved_credits,
                )
            )
            unknown_requirements.add(requirement.requirement_id)
            warnings.append(f"SHARED_SOURCE_USE_UNKNOWN:{binding.binding_id}")
            if source_exclusive > _ZERO:
                warnings.append(f"SHARED_SOURCE_CAP:{attempt.attempt_id}")
            continue
        requirement_capacity = max(_ZERO, requirement.max_credits - exclusive_amounts.get(requirement.requirement_id, _ZERO) - sum((item.credits for item in shadows if item.requirement_id == requirement.requirement_id), _ZERO))
        amount = min(binding.approved_credits, source_remaining, remaining_ledger, requirement_capacity)
        if amount > _ZERO:
            shadows.append(CreditPortion(attempt.attempt_id, requirement.requirement_id, amount, SHARED_SHADOW, direction, binding.binding_id))
            ledgers[direction] += amount
            shared_by_attempt[attempt.attempt_id] = shared_by_attempt.get(attempt.attempt_id, _ZERO) + amount
            ledger_binding_ids[direction].append(binding.binding_id)
            assessments.append(BindingAssessment(binding.binding_id, PASS, "exact VERIFIED shared binding", direction, amount))
        else:
            assessments.append(BindingAssessment(binding.binding_id, UNKNOWN, "shared credit has no available capacity", direction, binding.approved_credits))
            unknown_requirements.add(requirement.requirement_id)
            warnings.append(f"SHARED_CAPACITY_UNKNOWN:{binding.binding_id}")
        residual = binding.approved_credits - amount
        if residual > _ZERO:
            blocked[direction] += residual
            if source_remaining < remaining_ledger and source_remaining <= requirement_capacity:
                warnings.append(f"SHARED_SOURCE_CAP:{attempt.attempt_id}")
            if remaining_ledger <= source_remaining and remaining_ledger <= requirement_capacity:
                warnings.append(f"SHARED_LEDGER_CAP:{direction}:{binding.binding_id}")
            if requirement_capacity <= source_remaining and requirement_capacity <= remaining_ledger:
                warnings.append(f"SHARED_CAPACITY_UNKNOWN:{binding.binding_id}")
            unknown_requirements.add(requirement.requirement_id)
    ledgers_result = tuple(
        SharedLedger(direction, ledgers[direction], SHARED_LIMIT, blocked[direction], tuple(ledger_binding_ids[direction]))
        for direction in (PRIMARY_TO_TARGET, TARGET_TO_PRIMARY)
    )
    return tuple(sorted(shadows, key=lambda item: (item.direction, item.binding_id, item.requirement_id))), ledgers_result, tuple(assessments), unknown_requirements, warnings


def _evaluate_requirements(
    requirements: tuple[RequirementSpec, ...],
    exclusive_amounts: Mapping[str, Decimal],
    shadows: Sequence[CreditPortion],
    unknown_requirements: set[str],
    waived_requirements: set[str] | None = None,
) -> tuple[tuple[RequirementResult, ...], str, list[str]]:
    waived_requirements = waived_requirements or set()
    shared_amounts: dict[str, Decimal] = {}
    for portion in shadows:
        shared_amounts[portion.requirement_id] = shared_amounts.get(portion.requirement_id, _ZERO) + portion.credits
    results: list[RequirementResult] = []
    blockers: list[str] = []
    for requirement in requirements:
        exclusive = exclusive_amounts.get(requirement.requirement_id, _ZERO)
        shared = shared_amounts.get(requirement.requirement_id, _ZERO)
        effective = exclusive + shared
        deficit = max(_ZERO, requirement.credits_required - effective)
        # ``RequirementSpec.waiver`` only declares that a waiver is possible;
        # it is not student-specific evidence.  Only an independently
        # verified WaiverDecision can make this requirement waived.
        waived = requirement.requirement_id in waived_requirements
        if waived:
            # A waiver is a visible decision, not earned credit.  It can
            # satisfy the requirement only when the requirement evidence is
            # itself complete and verified.
            deficit = _ZERO
        requirement_blockers: list[str] = []
        waiver_unresolved = requirement.waiver and requirement.requirement_id in unknown_requirements and not waived
        if not requirement.required:
            status = NOT_APPLICABLE
        elif deficit <= _ZERO:
            # A curriculum waiver flag is not evidence by itself.  If the
            # student has ordinary earned credit covering the requirement,
            # that route remains usable; only a zero-credit waiver path needs
            # an approved waiver decision.
            evidence_unknown = requirement.requirement_id in unknown_requirements and not (
                waiver_unresolved and effective > _ZERO
            )
            if requirement.coverage_state == COMPLETE and requirement.evidence_state == VERIFIED and not evidence_unknown:
                status = PASS
            else:
                status = UNKNOWN
                requirement_blockers.append(f"REQUIREMENT_COVERAGE_UNKNOWN:{requirement.requirement_id}")
        elif requirement.requirement_id in unknown_requirements:
            status = UNKNOWN
            requirement_blockers.append(
                f"WAIVER_DECISION_REQUIRED:{requirement.requirement_id}"
                if waiver_unresolved
                else f"REQUIREMENT_EVIDENCE_UNKNOWN:{requirement.requirement_id}"
            )
        else:
            status = FAIL
            requirement_blockers.append(f"REQUIREMENT_DEFICIT:{requirement.requirement_id}")
        blockers.extend(requirement_blockers)
        results.append(
            RequirementResult(
                requirement.requirement_id,
                status,
                requirement.credits_required,
                exclusive,
                shared,
                effective,
                deficit,
                requirement.coverage_state,
                requirement.evidence_state,
                waived,
                tuple(requirement_blockers),
            )
        )
    statuses = [item.status for item in results if item.status != NOT_APPLICABLE]
    status = FAIL if FAIL in statuses else UNKNOWN if UNKNOWN in statuses else PASS
    return tuple(results), status, blockers


def allocate_credits(
    attempts: Any,
    requirements: Any,
    bindings: Any = (),
    *,
    search_limit: int = 10000,
    waiver_decisions: Any = (),
) -> AllocationResult:
    """Allocate immutable transcript attempts to exact requirements.

    The search is deterministic and bounded.  If the bound is exhausted the
    best known allocation is retained for inspection, but the result is forced
    to ``UNKNOWN`` and marked with a blocker so it can never become a
    speculative PASS.
    """

    normalized_requirements, requirement_issues = _normalize_requirements(requirements, with_issues=True)
    normalized_attempts, attempt_issues = _normalize_attempts(attempts, with_issues=True)
    normalized_attempts = _repeat_filter(normalized_attempts, normalized_requirements)
    normalized_bindings, binding_issues = _normalize_bindings(bindings, with_issues=True)
    normalized_waiver_decisions, waiver_issues = _normalize_waiver_decisions(waiver_decisions, with_issues=True)
    waived_requirements, waiver_assessments, waiver_unknown, waiver_warnings = _validate_waiver_decisions(
        normalized_waiver_decisions,
        normalized_requirements,
    )
    if waiver_issues:
        conflicting_waiver_ids = {
            issue.split(":", 1)[1]
            for issue in waiver_issues
            if issue.startswith("DUPLICATE_WAIVER_DECISION_ID:")
        }
        waiver_unknown.update(
            decision.target_requirement_id
            for decision in normalized_waiver_decisions
            if decision.decision_id in conflicting_waiver_ids and decision.target_requirement_id
        )
    input_issues = tuple((*requirement_issues, *binding_issues, *attempt_issues, *waiver_issues))
    requirements_by_id = {item.requirement_id: item for item in normalized_requirements}
    repeat_selection_winners, repeat_selection_unknown_groups = _repeat_selection_state(
        normalized_attempts,
        normalized_requirements,
    )
    valid_exclusive_bindings: dict[str, list[EquivalencyBinding]] = {}
    pending_binding_requirements: set[str] = set()
    binding_assessments_seed: list[BindingAssessment] = []
    attempts_by_id = {item.attempt_id: item for item in normalized_attempts}
    for binding in normalized_bindings:
        if binding.shared:
            continue
        attempt = attempts_by_id.get(binding.source_attempt_id)
        requirement = requirements_by_id.get(binding.target_requirement_id)
        if attempt is None or requirement is None:
            pending_binding_requirements.add(binding.target_requirement_id)
            binding_assessments_seed.append(BindingAssessment(binding.binding_id, UNKNOWN, "binding source/target is missing", binding.direction, binding.approved_credits))
            continue
        valid, reason = _binding_is_verified(binding, attempt, requirement)
        if valid and attempt.available_credits <= _ZERO:
            valid = False
            reason = "source attempt has no positive earned credit"
        if valid:
            valid_exclusive_bindings.setdefault(attempt.attempt_id, []).append(binding)
            binding_assessments_seed.append(BindingAssessment(binding.binding_id, PASS, "exact VERIFIED exclusive binding", binding.direction, binding.approved_credits))
        else:
            pending_binding_requirements.add(requirement.requirement_id)
            binding_assessments_seed.append(BindingAssessment(binding.binding_id, UNKNOWN, reason, binding.direction, binding.approved_credits))

    candidate_requirements: dict[str, set[str]] = {}
    unknown_candidates: set[str] = set(pending_binding_requirements)
    if attempt_issues:
        # A conflicting attempt ID means the course identity/credits are not
        # stable enough for any requirement to be reported as a formal pass.
        unknown_candidates.update(item.requirement_id for item in normalized_requirements)
    for attempt in normalized_attempts:
        candidate_requirements[attempt.attempt_id] = {
            binding.target_requirement_id for binding in valid_exclusive_bindings.get(attempt.attempt_id, ())
        }
        for requirement in normalized_requirements:
            if attempt.status == WAIVER and requirement.waiver:
                candidate_requirements[attempt.attempt_id].add(requirement.requirement_id)
                continue
            if any(
                binding.target_requirement_id == requirement.requirement_id
                for binding in valid_exclusive_bindings.get(attempt.attempt_id, ())
            ):
                # An explicit equivalency record is the authoritative route
                # for this pair; do not silently replace it with a bare
                # direct requirement ID and lose its credit cap/audit handle.
                continue
            direct = _direct_match(attempt, requirement)
            if direct is True:
                if (
                    attempt.repeat_group_id in repeat_selection_unknown_groups
                    and requirement.repeat_policy == BEST_ATTEMPT_ONLY
                ):
                    unknown_candidates.add(requirement.requirement_id)
                candidate_requirements[attempt.attempt_id].add(requirement.requirement_id)
            elif direct is None:
                unknown_candidates.add(requirement.requirement_id)

    limit = max(1, int(search_limit)) if isinstance(search_limit, (int, float, Decimal)) else 10000
    nodes = 0
    exhausted = False
    best_choices: list[AttemptAllocation] | None = None
    best_amounts: dict[str, Decimal] | None = None
    best_score: tuple[Any, ...] | None = None
    best_signature: tuple[Any, ...] | None = None
    best_signatures: set[tuple[Any, ...]] = set()
    # Prefer the deterministic best grade/credit attempt when a fixed repeat
    # group has more than one numerically viable route.  Equal-quality
    # attempts intentionally retain their tie so the caller can decide if
    # the records are truly interchangeable.
    repeat_quality_ranks: dict[str, int] = {}
    grouped_for_quality: dict[str, list[CourseAttempt]] = {}
    for item in normalized_attempts:
        if item.repeat_group_id:
            grouped_for_quality.setdefault(item.repeat_group_id, []).append(item)
    for grouped in grouped_for_quality.values():
        qualities = sorted({_attempt_quality(item) for item in grouped}, reverse=True)
        rank_by_quality = {quality: len(qualities) - index for index, quality in enumerate(qualities)}
        for item in grouped:
            repeat_quality_ranks[item.attempt_id] = rank_by_quality[_attempt_quality(item)]

    def score(choices: Sequence[AttemptAllocation], amounts: Mapping[str, Decimal]) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
        legalized = _legalize_choices(
            normalized_attempts,
            choices,
            requirements_by_id,
            repeat_selection_winners=repeat_selection_winners,
            repeat_selection_unknown_groups=repeat_selection_unknown_groups,
        )
        shadows, _ledgers, _assessments, shared_unknown, _warnings = _shared_projection(
            normalized_attempts,
            normalized_requirements,
            normalized_bindings,
            amounts,
            legalized,
        )
        unknown = set(unknown_candidates) | shared_unknown
        unknown |= _repeat_evidence_unknown(normalized_attempts, legalized, requirements_by_id)
        results, status, _blockers = _evaluate_requirements(
            normalized_requirements,
            amounts,
            shadows,
            unknown | waiver_unknown,
            waived_requirements,
        )
        pass_count = sum(item.status == PASS for item in results)
        unknown_count = sum(item.status == UNKNOWN for item in results)
        deficit = sum((item.deficit for item in results), _ZERO)
        recognized = sum((portion.credits for choice in legalized for portion in choice.portions if portion.allocation_kind == EXCLUSIVE), _ZERO)
        repeat_quality = sum(
            repeat_quality_ranks.get(choice.attempt_id, 0)
            for choice in legalized
            if _repeat_mode_for_portions(choice.portions, requirements_by_id) == BEST_ATTEMPT_ONLY
        )
        primary_status = 1 if status == PASS else 0
        # A definite academic deficit is more informative than an unresolved
        # coverage flag: when the same branch is numerically short, retain
        # FAIL instead of choosing an empty/unknown branch merely because it
        # has fewer UNKNOWN requirement rows.  Coverage still prevents PASS
        # once the numeric gate is met.
        return (primary_status, pass_count, -deficit, -unknown_count, repeat_quality, recognized), _signature(legalized)

    def visit(
        index: int,
        amounts: dict[str, Decimal],
        choices: list[AttemptAllocation],
        repeat_states: dict[str, tuple[str, str | None]],
    ):
        nonlocal nodes, exhausted, best_choices, best_amounts, best_score, best_signature, best_signatures
        if nodes >= limit:
            exhausted = True
            return
        nodes += 1
        if index >= len(normalized_attempts):
            current_score, current_signature = score(choices, amounts)
            if best_score is None or current_score > best_score:
                best_score = current_score
                best_signature = current_signature
                best_choices = list(choices)
                best_amounts = dict(amounts)
                best_signatures = {current_signature}
            elif current_score == best_score:
                best_signatures.add(current_signature)
                if current_signature < (best_signature or ()):
                    best_signature = current_signature
                    best_choices = list(choices)
                    best_amounts = dict(amounts)
            return
        attempt = normalized_attempts[index]
        options: list[tuple[tuple[CreditPortion, ...], Decimal]] = [((), attempt.available_credits)]
        for requirement_id in sorted(candidate_requirements.get(attempt.attempt_id, ())):
            requirement = requirements_by_id.get(requirement_id)
            if requirement is None:
                continue
            # A verified equivalency binding is the authoritative route for
            # this attempt/requirement pair.  Never add a bare direct option
            # that could spend more than ``approved_credits`` or lose the
            # binding audit identity.
            if any(
                binding.target_requirement_id == requirement_id
                for binding in valid_exclusive_bindings.get(attempt.attempt_id, ())
            ):
                continue
            option = _option_portions(attempt, requirement, requirements_by_id, amounts)
            if option is not None:
                options.append(option)
        # Explicit exact bindings are candidates even when the transcript
        # identity itself is not otherwise known.
        for binding in sorted(valid_exclusive_bindings.get(attempt.attempt_id, ()), key=lambda item: item.binding_id):
            requirement = requirements_by_id.get(binding.target_requirement_id)
            option = _option_portions(attempt, requirement, requirements_by_id, amounts, binding) if requirement else None
            if option is not None and option not in options:
                options.append(option)
        # A waiver is an explicit, auditable requirement decision.  Keep its
        # zero-credit portion visible even though the ordinary skip branch
        # has the same numeric score.
        if attempt.status == WAIVER and len(options) > 1:
            options = options[1:]
        for portions, residual in options:
            if not _repeat_option_allowed(
                attempt,
                portions,
                requirements_by_id,
                repeat_states,
                repeat_selection_winners=repeat_selection_winners,
                repeat_selection_unknown_groups=repeat_selection_unknown_groups,
            ):
                continue
            group_id = attempt.repeat_group_id
            repeat_mode = _repeat_mode_for_portions(portions, requirements_by_id)
            previous_state = repeat_states.get(group_id) if group_id else None
            if group_id and repeat_mode is not None and previous_state is None:
                repeat_states[group_id] = (repeat_mode, attempt.attempt_id if repeat_mode == BEST_ATTEMPT_ONLY else None)
            updated = _apply_portions(amounts, portions)
            choices.append(AttemptAllocation(attempt.attempt_id, attempt.available_credits, portions, residual))
            visit(index + 1, updated, choices, repeat_states)
            choices.pop()
            if group_id and repeat_mode is not None and previous_state is None:
                repeat_states.pop(group_id, None)

    visit(0, {}, [], {})
    if best_choices is None:
        best_choices = [AttemptAllocation(item.attempt_id, item.available_credits, (), item.available_credits) for item in normalized_attempts]
        best_amounts = {}
        best_score = (0, 0, 0, _ZERO, 0, _ZERO)

    assert best_amounts is not None
    legalized_choices = _legalize_choices(
        normalized_attempts,
        best_choices,
        requirements_by_id,
        repeat_selection_winners=repeat_selection_winners,
        repeat_selection_unknown_groups=repeat_selection_unknown_groups,
    )
    shadows, ledgers, binding_assessments, shared_unknown, shared_warnings = _shared_projection(
        normalized_attempts,
        normalized_requirements,
        normalized_bindings,
        best_amounts,
        legalized_choices,
    )
    requirement_unknown = set(unknown_candidates) | shared_unknown
    requirement_unknown |= _repeat_evidence_unknown(normalized_attempts, legalized_choices, requirements_by_id)
    requirement_results, status, blockers = _evaluate_requirements(
        normalized_requirements,
        best_amounts,
        shadows,
        requirement_unknown | waiver_unknown,
        waived_requirements,
    )
    all_binding_assessments = tuple(binding_assessments_seed) + tuple(binding_assessments)
    warnings = list(waiver_warnings) + list(shared_warnings)
    blockers.extend(input_issues)
    if not normalized_attempts and not normalized_requirements:
        blockers.append("EMPTY_INPUT")
    if not normalized_requirements:
        blockers.append("REQUIREMENTS_MISSING")
    if input_issues or not normalized_requirements or not normalized_attempts and not normalized_requirements:
        status = UNKNOWN
    if exhausted:
        status = UNKNOWN
        blockers.append("SEARCH_EXHAUSTED")
    if any(item.status == UNKNOWN for item in all_binding_assessments):
        warnings.extend(f"UNVERIFIED_EQUIVALENCY:{item.binding_id}" for item in all_binding_assessments if item.status == UNKNOWN)
    alternatives = tuple(sorted(best_signatures, key=repr))
    allocation_ambiguous = len(alternatives) > 1
    if allocation_ambiguous:
        # Any unresolved route choice is unsafe, including a branch that is
        # currently numerically deficient.  A later manual correction could
        # change which requirement receives the course.
        status = UNKNOWN
        blockers.append("ALLOCATION_AMBIGUOUS")
        warnings.append(f"ALLOCATION_ALTERNATIVES:{len(alternatives)}")
    elif shared_unknown and status == FAIL:
        # A verified-looking shared route with no usable source allocation is
        # unresolved evidence, not a definite academic failure.
        status = UNKNOWN
    active_ids = _active_attempt_ids(
        normalized_attempts,
        legalized_choices,
        requirements_by_id,
        repeat_selection_winners=repeat_selection_winners,
        repeat_selection_unknown_groups=repeat_selection_unknown_groups,
    )
    source_earned = sum((item.available_credits for item in normalized_attempts if item.attempt_id in active_ids), _ZERO)
    recognized = sum((portion.credits for choice in legalized_choices for portion in choice.portions if portion.allocation_kind == EXCLUSIVE), _ZERO)
    unallocated = sum((choice.unallocated_credits for choice in legalized_choices), _ZERO)
    conservation = recognized + unallocated == source_earned
    if not conservation:
        blockers.append("CREDIT_CONSERVATION_FAILED")
        status = UNKNOWN
    return AllocationResult(
        status=status,
        allocations=legalized_choices,
        requirement_results=requirement_results,
        source_earned_credits=source_earned,
        recognized_credits=recognized,
        unallocated_credits=unallocated,
        credit_conservation=conservation,
        shadow_allocations=shadows,
        shared_ledgers=ledgers,
        binding_assessments=all_binding_assessments,
        waiver_assessments=waiver_assessments,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        search_exhausted=exhausted,
        pass_eligible=status == PASS and not exhausted,
        nodes_searched=nodes,
        objective=best_score or (),
        alternative_allocations=alternatives,
        allocation_ambiguous=allocation_ambiguous,
    )


__all__ = [
    "AllocationResult",
    "AttemptAllocation",
    "BEST_ATTEMPT_ONLY",
    "BindingAssessment",
    "COMBINED",
    "COMPLETE",
    "CONFLICTED",
    "CreditPortion",
    "CourseAttempt",
    "EquivalencyBinding",
    "EXCLUSIVE",
    "FAIL",
    "LAB",
    "LECTURE",
    "MANUAL_REVIEW",
    "MISSING",
    "NONE",
    "NOT_APPLICABLE",
    "PARTIAL",
    "PASS",
    "PRIMARY_TO_TARGET",
    "REPEATABLE",
    "RequirementResult",
    "RequirementSpec",
    "SHARED_BLOCKED",
    "SHARED_SHADOW",
    "SHARED_LIMIT",
    "SharedLedger",
    "TARGET_TO_PRIMARY",
    "UNKNOWN",
    "VERIFIED",
    "WAIVER",
    "WaiverAssessment",
    "WaiverDecision",
    "allocate_credits",
]
