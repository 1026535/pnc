# Live failure reporting

Read this contract when preparing or executing a live-test batch, including a Devin assignment. Every popup, BlueStacks instance-management, and castle selection or identity-validation failure must produce a durable incident report. A batch entry or Devin manifest alone is not publication to the weekly collection.

## What to record

- `popup`: recognition, eligibility, dismissal or recovery failure, unexpected blocking popup, manual dismissal after canonical recovery fails, or a task-owned dialog misclassified or dismissed as a popup.
- `instance_management`: target resolution/selection, startup, readiness, freeze, ADB transport, lease/reservation admission, replacement, or cleanup failure. Record a foreign-reservation stop as an authority/precondition interruption, not evidence that reservation enforcement is defective.
- `castle_identity`: castle selection/switching failure, wrong account/castle, missing or mismatched identity proof, or lost continuity that prevents validation.

Include preflight failures before ADB access, recovered incidents, failures retained from cancelled or frozen runs, and failures before a feature case can start. Report only the boundary supported by the evidence; a worker transport crash alone does not establish an emulator freeze. Normal successful checks and normal handled popups remain in the batch/manifest, with `interruptions: []` when no incident occurred. A recovered interruption stays reportable even if every feature case eventually passes.

Reporting does not authorize live access, extra captures, retries, spending, account/instance/castle changes, code fixes, or coordinator messages. Use evidence from the authorized run or received handoff. Preserve popup-family eligibility rules: do not check or provoke an offer when it cannot occur. Unknown eligibility is an evidence gap, not permission to broaden checks.

## Shared destinations and ownership

The coordinator supplies an absolute `report_repository_root` in the batch and delegated brief: the primary checkout whose ignored collections the weekly job reads, not the disposable worker worktree. For this installation it is `C:/Users/lebel/pnc`. Resolve these paths against that root:

| Incident | Collection and record folder |
|---|---|
| Popup, including a popup with an identity/instance cause | `.local-data/reports/popup-audits/records/<incident-id>/` |
| Castle identity or instance management without a popup | `.local-data/reports/live-test-failures/incidents/<incident-id>/` |

Use one stable ID per occurrence, such as `INC-YYYYMMDD-<unique-run-id>-<ordinal>`. Declare a unique run ID before execution so concurrent workers create separate folders. Retain existing numeric IDs. Reuse an existing incident ID when the original run/frame and failed boundary match; related symptoms from the same occurrence belong in that record, not a duplicate in both collections. A recurrence in another run gets its own ID linked to the prior incident.

The tester owns writing its incident folders. At handback, the coordinator verifies each interruption's report path and notes any unindexed records. The collection's designated owner or weekly reporting job adds new popup records to `popup-audits/catalog.json` and `INDEX.md` according to `POLICY.md`, preserving existing entries and historical evidence. Workers and concurrent testing coordinators do not rewrite shared indexes. Weekly collection also reads record folders directly so an interrupted index update cannot hide a report; an index lag does not invalidate an otherwise published record.

## Publish at the first safe checkpoint

Record the failure before recovery when safe; otherwise protect the instance and release required resources first, then publish at the next safe checkpoint. Do not wait until the final handoff. Write `README.md` and `record.json` in the incident folder, then append dated recovery/disposition updates as facts become available. Keep the initial failure and every prior acceptance claim traceable.

`README.md` is the human report. `record.json` carries the same incident's searchable metadata using these fields (retain existing collection metadata when updating a record):

- `id`, `title`, `kind: "incident"`, `category`, `status`, `summary`, `record_path` relative to its collection root.
- `occurred_at` with timezone, `collected_at_utc`, and `evidence_dates`; occurrence time is unknown when not established, never inferred from file modification time.
- `batch_id`, `run_id`, `case_ids`, absolute batch and manifest paths when available, reporter and follow-up `owner` task/run references, `source_commits`, and tested source/import root. Record an uncommitted candidate's available source fingerprint instead of presenting HEAD as the exact tested tree.
- Non-sensitive intended and observed instance/account/castle identity; failed boundary, expected and actual behavior, recovery action/result, affected-case disposition, and next step.
- Observed/reported/inferred facts and unknowns, related incident IDs, fix revisions, offline validation, and live acceptance as separate fields. For popup geometry, include the saved frame dimensions and coordinate space when available; for offer checks, include established eligibility and its provenance. Missing facts stay explicit without new live observation.
- `sources`: original absolute path, collection-relative snapshot path, SHA-256 of the snapshot, collection time, and what it proves. Preserve the smallest useful existing screenshot, observation, trace excerpt or handoff under `sources/`; identify excerpts/redactions and their original provenance. Original raw evidence stays in its configured artifact root. Do not copy whole artifact trees or place raw evidence in `DEVIN_IMPLEMENT_TURN_DIR`. Exclude secrets, sensitive configuration, and reservation receipts. Mark missing sources explicitly rather than inventing paths or hashes.

Start at `reported`; recovery is an outcome, not a fixed/closed status. Preserve the popup collection's evidence-based status policy. Manual dismissal, a clean Home screenshot, absence of an offer, or a cancelled run does not establish automated recovery or live acceptance. Assign an unknown follow-up owner to the coordinating task for triage without guessing another task's commitment.

Link each incident ID and absolute report path from the batch's `Interruptions` and the Devin manifest's `interruptions` entry. Use an empty interruptions list only for an observed incident-free run; it cannot certify an unobserved or interrupted interval.

If the shared destination cannot be written, retain the partial report in the run's ignored local evidence area and mark `report_publication: pending` with the error and local path. Continue only otherwise authorized work; this does not itself call for user intervention. The coordinator publishes that record before closing the reporting handoff. After a worker crash or missing handoff, the coordinator uses the batch and specifically known saved artifacts to publish or complete a partial report for each supported incident, leaving outcome, cleanup, and identity unknown where unproven. Record an unobserved interval as a batch/manifest coverage gap, without inventing an incident. Do not rerun live actions to fill the report.

## Monday collection

The existing weekly PNC live-testing failure report reads popup `catalog.json` plus `records/*/record.json`, and `live-test-failures/incidents/*/record.json`, then reconciles referenced batches and curated manifests. It deduplicates by stable incident ID and original run/frame/boundary, distinguishes new occurrences, newly received older evidence, status changes and unresolved carryovers, and reports recovered failures separately from unresolved ones. Missing reports or unreadable sources are coverage gaps, not zero incidents. It writes `.local-data/reports/live-test-failures/YYYY-MM-DD.md` and links it from `popup-audits/weekly/INDEX.md`; collection is offline and never starts a new test or bug hunt.
