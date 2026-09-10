# Assumption And Evidence Matrix

Use this reference for every material plan review. Keep the matrix concise, but split claims when they require different evidence or can fail independently.

## Matrix

| ID | Plan location | Requirement or assumption | Provenance | Consequence if false | Verification method | Target | Status | Evidence | Required correction or next proof |
|---|---|---|---|---|---|---|---|---|---|

Stable IDs should reflect the owning slice, for example `ARENA-ENTRY-01` or `SCHED-OVERLAP-02`. The matrix is traceability, not a task backlog: every row must identify the source claim and the evidence that proves or disproves it.

## Provenance

- `user_requirement`: an explicit requested behavior or constraint.
- `stakeholder_confirmed`: a domain fact explicitly supplied by the user; preserve it unless contradictory authoritative evidence requires clarification.
- `repository_contract`: code, typed config, schema, test, or documented ownership that currently controls behavior.
- `artifact_observation`: a saved screenshot, observation sidecar, log, or run summary.
- `live_observation`: one bounded trace from a verified current target.
- `external_authority`: current primary documentation for a platform, API, standard, or policy.
- `inference`: a reasoned conclusion that has not been directly proven.

## Status

- `repository_answered`: current code/config/tests directly establish the claim at the required scope.
- `artifact_answered`: adequate current artifacts directly establish the claim.
- `live_observed`: a bounded current trace establishes the claim.
- `stakeholder_confirmed`: the user supplied the authoritative domain decision and no runtime rediscovery is required.
- `mutation_boundary`: safe evidence reached the last read-only state; the remaining proof needs explicit authorization.
- `live_blocked`: a bounded attempt reached a named environmental, selector, identity, or classification stop condition.
- `unproven`: required evidence is missing or too weak.
- `contradicted`: authoritative evidence conflicts with the plan claim.
- `not_applicable`: only for a plan claim that genuinely does not apply; explain why. Do not use this for an untested target cell.

For target execution matrices, use only `passed`, `applicability_skip`, or `blocked`, matching the plan's promotion contract.

## Evidence Strength

- A test name or green suite is evidence only after inspecting that the test covers the claim and would fail when the behavior regresses.
- A screenshot establishes visible state at one instant. It does not prove the preceding action, timing behavior, recurrence, or a successful mutation without same-trace evidence.
- OCR text can establish semantics, subject to recognition uncertainty. It does not establish a coordinate source when geometry-only input is required.
- Historical artifacts can answer stable layout questions only when version and context remain representative. Current or variable UI claims need a bounded live trace.
- A user-supplied domain fact should be recorded as `stakeholder_confirmed`, including its exact scope. Do not waste live actions re-proving it unless the user asks or runtime evidence contradicts it.
- Passing one target does not prove another target with a different account, castle level, unlocked feature set, screen layout, or live state.

## Findings

Each actionable finding contains:

- severity: critical, high, medium, or low;
- plan location and claim ID;
- concrete contradiction, omission, ambiguity, or weak evidence;
- authoritative evidence and its provenance;
- impact on implementation or unattended promotion; and
- correction direction that preserves one canonical implementation.

Do not report a style preference as a finding unless it causes ambiguity, duplication, unsafe execution, or unverifiable acceptance criteria.

## Readiness Verdicts

`implementation_ready` requires:

- no unresolved critical/high design contradiction;
- one canonical owner for each concept;
- material read-only assumptions answered;
- mutation boundaries and unknowns explicitly represented; and
- each slice has deterministic offline coverage plus an exact live proof path.

`promotion_ready` additionally requires:

- relevant focused and full offline checks passed;
- every named target cell is `passed` or an approved `applicability_skip`;
- live pre/postconditions and recovery were observed;
- prohibited adjacent actions remained unreachable or untouched; and
- no material row remains `unproven`, `contradicted`, `live_blocked`, or `mutation_boundary`.

## Primary Sources Behind The Method

- NASA's Systems Engineering Handbook uses requirement verification and validation matrices, bidirectional traceability, named verification methods, recorded environments/results, and discrepancy reporting: <https://www.nasa.gov/reference/system-engineering-handbook-appendix/> and <https://science.nasa.gov/wp-content/uploads/2023/04/nasa_systems_engineering_handbook_0.pdf>.
- NASA distinguishes verification of specified requirements from validation that the system functions as users expect in its intended environment: <https://www.nasa.gov/reference/5-0-product-realization/>.
- Google SRE recommends small, self-contained canaries with an explicit evaluation before broader rollout and warns that overlapping canaries contaminate attribution: <https://sre.google/workbook/canarying-releases/>.
- Android documents verifying the connected device and preserving screenshots as device-state evidence: <https://developer.android.com/studio/run/device> and <https://developer.android.com/tools/adb>.
- For Task Scheduler assumptions, use Microsoft's current documentation for logon type, task settings, and multiple-instance policy rather than local inference: <https://learn.microsoft.com/en-us/windows/win32/taskschd/principal-logontype>, <https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings>, and <https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-multipleinstances>.
