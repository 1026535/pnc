# Keeping Devin's PNC knowledge current

This procedure repeats the APK acquisition, Lua recovery, native tracing, and evidence publication performed in this task. The result is an accepted, versioned evidence snapshot and scoped reference updates that later Devin consultations can read. It does not make the client source authoritative about server rules or current UI state.

Use the existing [provenance recipe](PROVENANCE.md), [source map](SOURCE_MAP.md), and [request trace](REQUEST_PATH.md) rather than duplicating their build-specific facts here. The September 12 extraction is the baseline, not evidence that the installed game is still on that build.

## 1. Choose the smallest refresh

| Trigger | Work needed |
|---|---|
| A new question, with usable evidence already present | Trace only the affected workflow and propose a scoped note. No APK reacquisition. |
| Source directory missing in a worktree | Have the lead identify the existing evidence root or supply the required artifacts. Git does not copy ignored evidence into worktrees. |
| Newly supplied APKs or an authorized observation of a changed package | Inventory and hash the supplied package set, then recover and compare changed content. |
| UI behavior conflicts with a note, even at the same package version | Mark the disputed claim stale; inspect saved evidence first. A downloaded update or server-driven behavior remains possible. |
| A changed native binary affects a protocol claim | Revalidate the necessary native methods; do not carry RVAs or packet semantics forward by name alone. |

No calendar interval by itself proves evidence is stale or fresh. Do not launch a refresh on every consultation, or create a recurring job from this document. Record both the evidence acquisition date and the date a particular claim was checked.

## 2. Bind the assignment and permissions

The normal [Devin consultation](../../.agents/skills/devin-game-knowledge/SKILL.md) is read-only. Its launcher denies interpreters, dependency installs, ADB, and writes. Do not loosen that configuration to run this procedure. A consultation can identify stale claims and return a refresh proposal with `NEEDS_LEAD`.

An authorized maintenance assignment may instead give a Devin worker the exact offline artifact and documentation scope through the normal implementation workflow. The lead owns acceptance and integration. A refresh that also needs delegated live work follows [devin-live-test](../../.agents/skills/devin-live-test/SKILL.md) and the canonical [live policy](../../.agents/skills/test-bluestacks-live/SKILL.md); knowledge consultation is not a competing live session.

Before work, record:

- The question/workflows to refresh and the previous accepted evidence root.
- The task-owned checkout and exact repository base SHA. Use the source-control skill before tracked edits; preserve unrelated work.
- The supplied APK/evidence paths and a new ignored output directory. Resolve these explicitly when source and evidence live in different worktrees.
- Whether the assignment is offline-only. If acquisition is authorized, record the configured target, exact read-only acquisition, live owner, and any declared long reservation. The historical `157_farm` selection is not a default authorization for a new run.
- Allowed tracked paths and whether commit/push/integration are authorized. Writing a procedure does not authorize executing a refresh.

## 3. Acquire only when necessary and authorized

Skip this phase for supplied APKs. For a fresh acquisition, the assigned live owner creates the required batch and incident-reporting context, checks reservation status, and resolves the target through current config and canonical runtime. Hold a process-scoped task lease across dependent ADB operations. Use a declared long reservation only when the assignment requires ownership across phases, carrying its receipt without printing its contents. Follow the live skill for identity, readiness, cleanup, and incidents; do not bypass a foreign reservation or guess an endpoint.

Under that lease:

1. Record package name, versionName/versionCode, ABI, acquisition time, and the initial observable state. Apply current identity requirements before taking over the target; a failed baseline is not a feature result.
2. Obtain the installed package paths with package-manager inspection for the configured package, through the configured ADB client. Copy **all returned base and split APKs** into the new snapshot; do not assume three files or copy only base.apk.
3. Record each original split/path, local filename, byte size, and SHA-256. Validate the ZIP archives. Recheck package identity/version and split paths after copying; an observed installation change leaves the set incomplete until a stable acquisition is possible.
4. Release task leases and preserve pre-existing instances. Release a long reservation only at its declared terminal scope. Record failures through the canonical incident workflow, including recovered setup failures.

Do not replay the historical `explore.py` acquisition script unchanged: it embeds the old target, directory, and release marker. Use current lease/runtime interfaces. This acquisition reads packaged client files; it does not collect credentials, private account storage, or session tokens. Do not automatically expand it into runtime hooking, traffic interception, API calls, or game actions.

## 4. Build a new offline snapshot

Preserve the accepted baseline. Use a new path such as `.local-data/apk-exploration/snapshots/<versionCode>-<date>-<run-id>/`; never overwrite an older extraction to make it look current. Keep analysis tools and dependencies in ignored local storage, recording versions. Do not alter project dependencies for artifact inspection.

Write a small `evidence-manifest.json` in the snapshot with these concrete fields:

| Field | Contents |
|---|---|
| `snapshot_id`, `acquired_at`, `analyzed_at` | Unique run identity and timestamps |
| `package`, `version_name`, `version_code`, `abi` | Observed package metadata, not inferred from a filename |
| `repository_sha`, `baseline_snapshot` | Checkout used and previous accepted evidence |
| `apk_files` | Split identity, local path, size, SHA-256, archive-check result |
| `tools`, `extraction` | Tool versions, input member, discovered chunk/bundle location, encoding, file counts, and failures |
| `indexes`, `checks`, `limitations` | Relative output paths, actual check results, and missing/ambiguous evidence |
| `status` | Candidate, accepted, or incomplete; acceptance owner/date when applicable |

This is an evidence record, not a new runtime registry. Do not include credentials, reservation receipt contents, account payloads, or raw local configuration.

Inventory ZIP members before selecting an engine-specific decoder. The recorded build has Unity assets, `global-metadata.dat`, `libil2cpp.so`, and `libslua.so`. If that structure changes, state what was observed and revise the extraction diagnosis rather than forcing the old parser.

## 5. Locate and recover gameplay Lua

For the exact hash-matched baseline, use the reproducible recipe in [PROVENANCE](PROVENANCE.md). Its chunk number, offset, XOR byte, and file count are **build-specific**. For a new package:

1. Enumerate actual asset chunks. In the recorded format, `ABAsset.pkglzma_*` members decompress with LZMA into concatenated UnityFS bundles. Walk each bundle by its declared length, validating bounds; do not seek directly to the historical offset.
2. Parse bundles with a compatible Unity asset reader. Index TextAssets by **original container path**, source APK/chunk/bundle offset, size, and content hash. Keep localization/configuration separate from gameplay implementation. A basename alone can collide across directories or bundles.
3. Locate entry points such as `GameLuaMain` and follow metadata loader clues (`LuaManager`, `LoadLuaByteSync`) when necessary. Lua paths embedded in prefabs are references, not recovered source. Do not treat missing or unparsed bundles as deleted code.
4. Determine the encoding on known candidates. The recorded payloads decode by XOR with `0x2C`; test that hypothesis on the candidate build. Inspect entry points and a representative request/response file for coherent source. UTF-8 decoding or an XOR round trip alone does not prove the transform is correct. Stop and record the gap if the payload is bytecode, differently encoded, or not located.
5. Export without executing game scripts. Preserve bytes and directory structure, check resolved paths remain under the snapshot, and avoid silent duplicate overwrites. Produce `gameplay-lua-index.json` with original asset path, exported file path, byte size, and SHA-256. Record unsupported assets and parser failures.
6. Verify saved hashes against decoded payloads. For a newly discovered layout/transform, independently reproduce the affected extraction and compare outputs. Reuse existing passing proof when the inputs and decoder are unchanged.

The previous `scan_lua.py`, `export_gameplay.py`, and related scripts are useful local examples, not a maintained cross-version CLI. Inspect their hard-coded input/output roots, offsets, and decode assumptions before adapting them. They may be absent from another machine; the tracked provenance recipe and the steps above describe the actual operation.

## 6. Compare content and refresh only affected claims

Compare old and candidate indexes by original asset path and decoded SHA-256. Record added, changed, unchanged, removed, and unresolved/duplicate paths. A change in APK hash alone does not establish a gameplay change; identical gameplay files can be repackaged. An incomplete scan cannot establish deletion.

For each affected documented workflow, follow:

```text
UI handler -> local predicates -> request wrapper and sender hooks
           -> response registration/handler -> state updates -> observable postcondition
```

Inspect relevant shared state/config helpers when their content changed; an unchanged UI handler does not prove unchanged behavior if its dependencies changed. Prioritize workflows named in the assignment and shared code they use. Leave other notes explicitly tied to their prior build until checked; do not declare all workflows current because extraction completed.

Use the repository's finding labels (`user-confirmed`, `repository-proven`, `artifact-observed`, `live-observed`, `inferred`, `unknown`) and confidence. Decoded client source is **artifact-observed client behavior**, not a live-observed result or a server guarantee. A note needs snapshot/build, source path and symbol (line when useful), inspected predicates/state transitions, automation implications, and remaining uncertainty.

If package hashes are unchanged but current UI evidence conflicts, keep the discrepancy open. Inspect saved screenshots/runtime evidence or propose the smallest supported UI observation through the live owner. Do not claim this package refresh captured downloaded patches or server configuration, and do not silently copy private runtime storage to close the gap.

## 7. Retrace native code only when it changes the answer

For a changed native dependency or a protocol-specific question, extract matching `libil2cpp.so` and `global-metadata.dat` from the **same candidate package set**. Use a parser that supports the observed metadata version, recording its version and warnings. The baseline native reproduction steps are in PROVENANCE.

Map method addresses through ELF segments and inspect real ARM64 instructions. `dump.cs` has empty method bodies and establishes declarations only. Rediscover `LuaManager.SimpleInstrSend` and follow conversions, instruction construction, optional handlers, serialization, queueing, and the final send call. Do not transplant old RVAs, field offsets, checksum, or frame layout into a new build.

Only reconstruct a serializer/checksum when needed by the question. Compare a changed pure routine with isolated offline emulation on relevant synthetic inputs; do not execute an app entry point or make a game request. Record exactly what the check proves. Connection/login and server acceptance remain unknown unless separately established under an authorized task.

## 8. Accept and expose the evidence to Devin

The maintenance worker returns the candidate manifest, content delta, updated scoped notes, checks, and unresolved claims. The lead verifies the input provenance and the evidence supporting material changed claims. Mark a candidate accepted only for the coverage actually established; a parser's zero exit is insufficient.

Update the smallest set of maintained entry points in the owned checkout:

- [PROVENANCE](PROVENANCE.md): accepted snapshot/build binding and hashes, preserving historical provenance.
- [SOURCE_MAP](SOURCE_MAP.md) and affected `workflows/` notes: changed paths and verified findings. Preserve old build labels for untouched claims.
- [REQUEST_PATH](REQUEST_PATH.md): only for verified transport changes.
- [Devin evidence map](../../.agents/skills/pnc-game-knowledge/references/evidence-map.md): point to the accepted snapshot and refresh its compact digest. Keep historical addresses/counts labeled with their build; do not present them as candidate facts.
- [Devin expertise skill](../../.agents/skills/pnc-game-knowledge/SKILL.md): update discovery/build summaries only if needed; preserve consultation permissions and its memo contract.

Bind the accepted evidence root in future Devin assignments. For worktree-local runs, supply only the required snapshot artifacts through the existing path-scoped consultation allowance; do not widen its deny rules, change it to a writing session, or assume ignored files arrived through Git. Durable knowledge lives in the accepted artifacts and tracked notes, not a past worker's conversation memory.

Check changed Markdown links and `git diff --check`; validate a changed skill with its applicable validator. Documentation-only maintenance needs no unit/live suite. If an extraction helper was changed, run the smallest meaningful input/output check. Commit, push, and main integration occur only when included in the maintenance assignment. Report task-owned uncommitted paths and the final Git state.

## Reusable assignment and handback

Fill these fields with real paths/scope before assigning a maintenance worker:

```text
Refresh PNC game knowledge using docs/game-reference/MAINTENANCE.md.
Owned checkout and base SHA: ...
Previous accepted evidence root/snapshot: ...
Candidate APKs or supplied artifacts: ...
New ignored snapshot directory: ...
Workflows/questions to revalidate: ...
Allowed tracked documents/skill references: ...
Execution: offline only, unless a separate live assignment specifies otherwise.
Commit/push/integration authority: ...
Return the manifest, asset delta, scoped findings, checks, remaining stale/unknown
claims, and exact modified paths. Do not promote the evidence as accepted yourself
when lead acceptance is required; do not contact game servers or read credentials.
```

Use the normal `Answer`, `Findings`, `Automation implications`, `Next smallest observation`, and `Handback` memo sections, attaching artifact paths in the response. `READY_FOR_REVIEW` means a candidate is ready for the lead, not that all game knowledge is current. Return `NEEDS_LEAD` for missing evidence/authority or material ambiguity, with the exact next owner/action. Include lease/reservation cleanup and incident IDs if a separately assigned acquisition was performed.
