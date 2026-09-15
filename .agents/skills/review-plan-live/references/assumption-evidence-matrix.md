# Assumption And Evidence Matrix

Use a matrix only when several consequential plan claims need traceability. A short review should use ordinary findings instead.

| ID | Plan location | Material claim | Why it matters | Evidence or method | Status | Correction or next proof |
|---|---|---|---|---|---|---|

Include claims whose failure would change architecture, safety, acceptance, or likely behavior. Omit cosmetic details, implementation trivia, and remote theoretical cases.

## Provenance And Status

Identify evidence as user-confirmed, repository-proven, artifact-observed, live-observed, externally authoritative, inferred, or unknown.

Use concise statuses:

- `answered`: adequate evidence supports the claim;
- `mutation_boundary`: proof requires an unauthorized state change;
- `blocked`: a bounded attempt could not obtain required evidence;
- `unproven`: material evidence is absent;
- `contradicted`: authoritative evidence conflicts with the plan; or
- `not_applicable`: the claim genuinely does not apply, with a reason.

Use target results `passed`, `applicability_skip`, or `blocked` only when multiple targets are justified by the plan's contract or observed variation.

## Evidence Bar

- A test supports a claim only when it exercises the behavior and would fail on regression.
- A screenshot proves visible state at one moment, not an unobserved transition.
- Historical UI/runtime evidence can support stable behavior when its version and context remain representative.
- Preserve user-supplied domain decisions unless material repository or runtime evidence contradicts them.
- One representative target is sufficient unless target differences matter to the claim.

## Verdict

`implementation_ready` requires no unresolved high-impact design or safety issue and a credible verification path. `promotion_ready`, when in scope, additionally requires the live-dependent behavior to be proven on the justified target set.

Do not withhold readiness for low-impact unknowns that do not change the design or acceptance decision; state them briefly as residual risk.
