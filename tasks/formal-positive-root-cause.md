# Formal positive path: bounded root-cause report

## Assessment

The Earth 111 probe is not invalid merely because its AG102-style rows omit course numbers. It supplies confirmed course name, credits, term, completion status, and component, which is the supported no-code identity path. The formal failure has three independent runtime causes: a numeric key mismatch prevents exact handbook identity resolution; authoritative public-catalog pool evidence is lowered to UNKNOWN; and an obsolete post-pass marks implemented aggregate pools as `RULE_NOT_IMPLEMENTED`. After those are corrected, the 68-row case still needs allocation-first search ordering so a feasible witness is reached before the 10,000-node optimization bound. Search exhaustion without a witness already remains UNKNOWN rather than a confident FAIL.

## Findings

### HIGH — equal credit values use unequal lookup keys

`_compile_attempts()` indexes no-code candidates with `(normalized_name, str(credits))` and performs the same string-based lookup (`graduation_service.py:2261-2295`, `2634-2644`). In the actual probe, the confirmed row becomes `Decimal('2')` while registry metadata is `Decimal('2.0')`. The numeric values are equal, but the keys `"2"` and `"2.0"` differ. Result: all 68 attempts had `identity_status=UNKNOWN`; only 18 allocator edges were definite and 65 attempts produced at least one UNKNOWN match.

Smallest correction: type `catalog_by_name` as `dict[tuple[str, Decimal], ...]` and use `_positive_number(...)` directly in both insertion and lookup. Use the Decimal value in the duplicate candidate key as well. Do not round or convert through float/string.

Required regression: a no-code confirmed row with credit `2`, `2.0`, or `"2.00"` must resolve to the same unique official handbook identity when name/component match. A genuinely different credit value must not match.

### HIGH — VERIFIED public catalogue membership is not authoritative in allocation

`allocation_engine._direct_match()` permits an unresolved course identity to enter an eligible pool only when the membership evidence kind is exactly `policy` (`allocation_engine.py:1433-1469`). `resolve_public_evidence()` produces server-owned, term-bound, VERIFIED evidence with kind `public_catalog`; consequently a valid GE course remains `REQUIREMENT_EVIDENCE_UNKNOWN`. This reproduces in the parent's two-course/minimum-2 test, independent of the 128-credit search.

Smallest correction: for an aggregate/pool requirement, treat a VERIFIED membership whose kind is in an explicit trusted set `{policy, public_catalog}` as authoritative for that pool. This authority applies only to `RequirementSpec.kind == "AGGREGATE"` (or the existing explicit pool/quota kinds); it must not promote the attempt to a named-course identity. Continue rejecting missing, legacy, unverified, conflicted, or caller-provided membership. The confirmed-row sanitizer does not expose pool membership as a user field; membership must still originate from the server resolver.

Required regression: two completed 2-credit public GE rows, one with lecture and one with omitted component, satisfy a verified/complete 2-credit category pool through official membership. The same rows with a user category claim, missing official term match, or unverified membership remain UNKNOWN and allocate zero to that pool.

### HIGH — implemented quota rows are unconditionally relabelled as missing catalogues

After allocation, `evaluate()` builds `generic_ids` from every generic requirement except a verified policy (`graduation_service.py:4025-4034`). `_with_generic_unknown()` then overwrites those results with `RULE_NOT_IMPLEMENTED` and `REQUIREMENT_CATALOG_PARTIAL` (`graduation_service.py:3743-3778`). This discards registry truth even when the requirement and its candidate pool are VERIFIED/COMPLETE.

Smallest correction: mark only rows created by `_unresolved_threshold_quotas()` with explicit private compiler metadata such as `unresolved_catalog: true` (`graduation_service.py:2160-2205`). Pass only those IDs to `_with_generic_unknown()`. Explicit registry quota rows must be decided by their own evidence/coverage and actual membership results. Do not infer “unresolved” from `generic=True`.

Required regression: a VERIFIED/COMPLETE aggregate with a nonempty official candidate pool may PASS; a synthetic unresolved threshold placeholder remains UNKNOWN with both existing blocker codes.

### MEDIUM — bounded DFS explores skip branches before useful allocations

`allocate_credits()` initializes every attempt's option list with “allocate nothing” and visits it first (`allocation_engine.py:2669-2895`). Attempts are hash-sorted rather than constraint-sorted. Even after simulating canonical credit keys and authoritative public membership in memory, the Earth probe reached 10,000 nodes with no witness and only 15 recognized credits. This is search order, not evidence that the curriculum is infeasible.

Smallest safe correction: preserve the existing solver and `complete_witness()` validator, but search allocation options before the skip option. Order attempts by ascending count of definite candidate requirements, then stable attempt ID; order candidate requirements by named/exact before aggregate and by remaining scarcity. As soon as a complete, conserved witness is encountered, retain it exactly as current code already does (`allocation_engine.py:2913-2997`); later exhaustion reports `FEASIBLE` with `optimality=BOUNDED_NOT_COMPLETE`. If the bound expires before any witness, retain UNKNOWN/`SEARCH_EXHAUSTED`; never return FAIL from an incomplete search.

This is a search-order correction, not a new optimization architecture. The two-course GE regression must pass without relying on a higher limit. The 68-row probe is the integration case confirming that the heuristic reaches at least one complete witness under the default limit.

## Validation

Run in this order:

1. Decimal-scale identity regression.
2. Parent's two-row GE formal test; assert allocation and requirement PASS, trusted membership visible, and no `REQUIREMENT_EVIDENCE_UNKNOWN`.
3. Explicit aggregate versus unresolved-threshold tests for `_with_generic_unknown()`.
4. `tmp/formal_earth_probe.py`; require 128 source credits, positive conserved allocation, `feasible_witness=true`, and no `RULE_NOT_IMPLEMENTED`, `REQUIREMENT_CATALOG_PARTIAL`, `SEARCH_EXHAUSTED`, or `ALLOCATION_AMBIGUOUS` blockers. Non-credit metadata may remain a separate WIP result until its assigned adapter changes land.

## Delegation

Implementation belongs to the active Core `terra_worker`. The public resolver/data worker should keep emitting truthful server-owned `public_catalog` evidence and must not rewrite it as `policy` merely to bypass `_direct_match()`.
