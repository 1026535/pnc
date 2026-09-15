# Remaining package 05 — Mail sending and Login

Evidence snapshot: September 14, 2026; scope revised September 15, 2026. This package contains the original A08
Send Mail and A03 Login remainders. They share one vertical owner and entrypoint
surface, but have separate implementations and acceptance gates. Read the
[independent package contract](PNC_CORE_WORKFLOW_PORTING_PLAN.md#six-remaining-agent-packages)
for shared scope only; this plan's named Mail/Login partitions govern its feature
files and symbols. Use the current assignment's verified checkpoint and this
planning revision; the old merged `6bc2758` is historical source context. Reuse a
suitable existing isolated task worktree and create/use the feature branch there;
do not create a second worktree merely for a preferred path. Preserve resumed
feature work; use a new worktree only if the current checkout is shared or
unsuitable. Follow the [common starting-checkpoint rules](PNC_CORE_WORKFLOW_PORTING_PLAN.md#common-starting-checkpoint-and-evidence-rules).
Do not rely on a dirty predecessor. Preserve newer implementation and apply the
current scope amendment before historical starting or live instructions.
Status: implementation may proceed; Mail live Send needs the user's recipient
kind/name/kingdom and exact subject/body, and Login needs the intended sign-in
method plus qualified observations for that route. These are direct user inputs
that this package must request when needed. The saved Compose checkpoint already
fixes the field interiors and both observer paths' requested-only field behavior,
including exact body spaces and punctuation; it contains no send or delivery
receipt. The native provider route is email-only with Log In, which is a separate
contract from the legacy username/password/Continue route.

## V01–V43 boundary

Read the [remaining-feature scope amendment](PNC_CORE_REMAINING_VISION_BOUNDARY.md).
V01 supplies the existing shared OpenCV/observation extension contract. Reuse its
matcher, bounded OCR, canonical additions and both-path publication; do not add a
new engine, global guard policy or duplicate parser framework here.

V01–V43 do not deliver Mailbox, player-profile/Compose/send-receipt or actual
Login/provider recognition. Their feature-local screens, controls, parsers,
routes and qualification remain in this package. Reuse already-qualified Mail
work; fix only missing supported-contract behavior. A profile route traversing a
V-owned surface consumes that packet's content/navigation rather than extending
its menu here. Alliance Hall reinforcement (V37) is not an alliance-member Mail
route, and Castle building information (V41) is not account authentication.

No waiting for all 43 plans or repeating V01 qualification is required. Record
any specific shared-output dependency actually consumed; continue independent
Mail/Login work. Future execution uses the current session's explicit target/action
authority under the scope amendment; historical captures supply evidence only.

### Saved evidence locations

Historical ignored `core_resume/` evidence resolves under
`C:/Users/lebel/pnc/.local-data/worktrees/workflow-recognition-integration/.local-data/artifacts/`.
Historical B `.local-data/reports/` diagnostics resolve under
`C:/Users/lebel/pnc/.local-data/worktrees/non-yolo-recognition-continuation/.local-data/reports/`.
Other numbered capture paths use the exact roots in the linked capture-findings
record. Read these saved artifacts in place; they are not copied into a new
feature worktree. Tracked fixtures arrive with the merged base. Put this feature's
new captures, replays and reports under its own ignored `.local-data/` and test
selection under `.test-impact/`. Missing historical evidence is reported with its
exact source path, never replaced by a guessed current screen or invented result.

## Outcome and existing boundaries to preserve

Mail: migrate the existing player/alliance send contract to one typed core path
that verifies its recipient and fields, sends once, observes a correlated new
receipt and returns Home. The existing typed collect-mail/archive workflow is
already implemented and is a dependency, not another deliverable here.

Login: migrate the existing Login and account-session preparation callers to a
bounded typed lifecycle path for the user's actual sign-in method. Separate
readiness, accessible-character evidence and verified account identity. A Home
screen or remembered roster is not automatically proof of the configured account.
Preserve the canonical startup/readiness owner and move only the remaining Login
behavior; do not rebuild emulator discovery, leases or general recovery.

Do not combine these tasks into one workflow, add mail scheduling, send a default
message, implement all identity providers, alter credentials/config to fit a test,
or reuse an unrelated Daily mutation capability for authentication or messaging.

## Required starting evidence and code map

Inspect the actual assigned isolated checkout and record its revision/status.
Preserve resumed commits and task-owned edits; do not reset to the historical
`6bc27585fbac1244672cf4a653ea6248955a4aca` snapshot. Read current root/scoped
`AGENTS.md`, applicable skills and
[CORE_WORKFLOW_PORTING](../instructions/CORE_WORKFLOW_PORTING.md).

| Area | Existing canonical owner or evidence to inspect |
|---|---|
| Mail input | `pnc_automation/app/pnc/domain/mail.py`: `SendMailParams`, `PlayerProfileRoute`, canonical parse/serialize helpers; `pnc_automation/app/pnc/enums/mail.py` |
| Legacy Mail behavior to migrate | `pnc_automation/app/automation/tasks/send_mail_task.py`: compose-target validation, profile-target capture, send phases, mailbox/thread verification |
| Closest typed send pattern | `pnc_automation/app/automation/send_chat.py`, constrained `WorkflowContext.send_chat_message`, existing `NavigationCore` send implementation |
| Existing mail navigation/storage | `pnc_automation/app/automation/collect_mail.py`, `navigation_core.py`, canonical mail archive store and parser; collection is not a send receipt |
| Login contract | `pnc_automation/app/automation/tasks/login_task.py`: configured-account checks, session/roster evidence, account-switch and login actions |
| Bootstrap/callers | `core_script_dispatcher.py:_execute_lifecycle_step`, `script_runner.py:prepare_account_session` and `_prepare_account_session_steps`; registry, application/API/session/module wrappers |
| Real captures | [Capture findings](PNC_NON_YOLO_CAPTURE_FINDINGS_20260913.md): Mail 0010–0018 and native account 0197–0203; no Send or credential submission occurred |
| Source behavior | [Mail sending note](../docs/game-reference/workflows/mail-sending.md), game reference [source map](../docs/game-reference/SOURCE_MAP.md) and [provenance](../docs/game-reference/PROVENANCE.md) |

Use `rg` to enumerate actual `TaskId.SEND_MAIL`, `TaskId.LOGIN`, `send_mail`,
`send_alliance_mail`, player-profile mail helpers and preparation callers at the
execution snapshot. Include CLI/authored paths that route through these owners.
Do not assume a helper is migrated because its public signature remains present.

The inspected APK is PNC 5.0.203 / 233; later live builds differ. Mail's
`MailWriteWin:OnSendHandler` has progress/level/self-send checks and uses different
player/private-chat and alliance send branches. Its success update closes Compose,
but ordinary Close also closes it. These facts identify meaningful tests; they
do not establish current server rules or authorize direct game-service calls.

For Login, the saved current provider route has an email field and Log In,
without the legacy password/Continue controls. `server/jufeng/gameloginmanager.lua`
and `datas/logindata.lua` are discovery pointers, not a verified current handshake.
After the user names the method, inspect only its relevant UI/callback chain and
record a scoped source note if it establishes reusable behavior. Never dump login
payloads, tokens, credential values or the entire extracted source.

The saved producer audit at commit `10740ebb9b8d9d43fc24f970b904796ca41bd082`
is retained as evidence, not as a handoff or consumer acceptance result. Its
saved Compose replay exercises both `ObservationBuilder` and
`NavigationPerception` paths and qualifies the centered Compose identity, field
interiors and actionable Send control without dispatching Send. Mail/Login owns
any additional feature-specific producer corrections, models, bounded OCR,
fixtures and qualification needed by the current contract. Generic vision
engines and the Resource-partial, Hero-results and broader-Research/Institute
families remain outside this plan. Use saved evidence first; do not repeat a
proven recognition mutation merely to qualify a consumer.

## Questions and permission ledger

| Decision or action | Current status | Agent handling |
|---|---|---|
| Live account, instance, configured role and action authority | Supplied by the current execution assignment/session | Record the applicable authorization and target in the run manifest; preserve it without asking again. This plan supplies no default account or unlimited budget. |
| Exact Mail recipient and subject/body | Asked; pending; this package asks the user directly | Obtain the recipient kind, exact name and kingdom, and approved subject/body before Send. Prefer another character owned by the user, not the active sender: the inspected client rejects self-send. Do not invent a nonce or change approved text silently. |
| Alliance broadcast, if chosen for a live proof | No exact audience/payload supplied; this package asks the user directly | Require the actual alliance audience and exact message before broadcasting. A player-mail answer is not an alliance-send instruction. Offline alliance coverage can proceed. |
| Intended Login method for the assigned account | Use the current session's answer; ask only if still missing | Record the named method when supplied, without sending credentials. Do not silently replace the legacy username/password contract with an email-only flow. |
| Provider consent, email-link/code or MFA interaction if required by that method | Conditional on discovered real route | Request the exact needed user interaction at that point. Keep secret entry in the configured secure channel or user-operated UI; do not put secrets in chat/docs. |
| Controlled logout/sign-in on the same assigned account | Requires applicable explicit session authority and a concrete recovery route | Preserve authorization already supplied; establish the supported method and required configured credentials/operator step before disrupting the session. Do not infer logout permission from this plan or access a second account. |
| Adding live roles, changing credentials/account configuration, enabling automatic Daily, merge/push | Not part of this planning or implementation package | Report the exact separate change if it becomes necessary. Never change config merely to pass a role/identity guard. |

These missing details gate only the dependent live action/contract. They do not
block repository inspection, deterministic validation design or supported Mail
navigation work. If the user answers during execution, record the answer here
or in a linked nonsecret run manifest and continue without repeating the question.
This package owns these already-identified user questions and must ask for the
missing details directly when the dependent live action or contract is reached.
Do not infer a recipient, payload, provider method or test audience. The alternate
castle target and SELECT_CASTLE semantics belong to package 06, but this package
does not wait for or jointly edit that behavior.

The vertical write boundary is explicit. Mail owns `SendMailParams`, send-specific
matching/receipt helpers and the `MailRecipientKind`/profile-route partitions;
Login owns its provider contract, identity result and `TaskId.LOGIN` lifecycle
behavior. Mail/Login owns only the named Mail/Login entries and profile/data keys
in `screen_type.py`, `ui_element_id.py`, `selector_registry.yaml`,
`screen_anchors.json`, `ocr_region_plan.py`, `observation_request.py`,
`pnc_observation_enricher.py`, `screen_classifier.py` and `observation.py`, with
fixtures and qualification tests for both observer paths. It also owns the named
Mail/Login methods in `navigation_core.py`, `core_workflow.py`,
`core_script_dispatcher.py`, `script_runner.py`, the registry and entrypoints.
Generic OCR/guard/runtime/lease/recovery engines stay unchanged. `TaskId.SELECT_CASTLE`,
castle-roster scanning, current-castle selection and synthetic optional-task
alignment retain their existing package 06 semantics; Login may consume their
post-authentication result but never introduces a second scanner or selector.

## M1 — Close the Mail contract and producer gate

Retain `MailRecipientKind.PLAYER` and `ALLIANCE`. Player requests currently accept
exactly one of `player_name` or `profile_route`; route kinds are player territory,
chat message, alliance member and Might Rank. Preserve this finite public contract.
The current `SendMailParams` fields are `recipient_kind`, `player_name`,
`profile_route`, `subject` and `body`; kingdom is not currently represented.
Before enabling a live player send, this package must resolve whether kingdom is
supplied by the selected `PlayerProfileRoute` or becomes an explicit contract
field. Do not smuggle kingdom through a name, fixture or matcher default.
For each route identify the existing typed navigation support and qualified
profile/Compose producer. Implement supported routes first; mark any unqualified
original route explicitly blocked, not silently omitted from package completion.

Mail/Login retains the following uncovered feature-specific producer work.
V01 shared integration and all V-owned menus remain dependencies to consume,
not implementation assignments here:

- Independent correct mailbox, player profile and Compose identities, requested
  recipient kind, actionable fields/Send and visible field state after editing.
  The corrected bottom-left Compose control proves only Compose entry.
- The published Compose checkpoint must be replayed independently through both
  real observer paths with frame-local screen/layout/guard provenance. Its
  requested-only field interiors are the producer contract: recipient, subject
  and body values must be verified in their own controls, with missing,
  unknown, empty and stale states kept distinct. Preserve exact body spaces and
  punctuation; do not normalize them into a first-line or substring assertion.
  This producer replay is no-send evidence and does not supply a delivery
  receipt.
- Current exact profile recipient when using a profile route; visible Compose
  target after opening it. A cached profile name cannot authorize a different
  current recipient. If kingdom disambiguation is required but absent from the
  current API/observation contract, record that gap before sending; do not invent
  kingdom metadata or select the first similarly named player.
- Supported success/error/eligibility observations and meaningful mailbox/thread
  content for a new send. Request explicit unavailable/unknown dispositions for
  fields the current UI cannot expose. Missing body or sender/recipient evidence
  must not be treated as empty matching content.

The original helper accepts a subject or first-body-line substring in any visible
candidate as mailbox-only proof, without a before-send delta. That is too weak to
prove a new action when the same text already exists. Refactor the canonical
matching semantics into their existing domain owner as needed, with a before/after
correlation contract. Do not maintain one permissive legacy matcher and a duplicate
core matcher. Preserve normalization appropriate to mail text while requiring the
intended recipient and new-message evidence; do not relax castle identity checks.

Acceptance: every supported send route names the actual producer facts it consumes
and an achievable positive receipt. A toast alone, Compose disappearance or an old
matching thread cannot become confirmed delivery. If existing observations cannot
support correlation, stop promotion at that exact producer gap.

## M2 — Implement one typed compose/send/verify path

Add a dedicated Mail workflow/result following the typed Chat pattern and the
existing Mail domain parser. Proposed result data should distinguish a send
attempt from confirmed sent proof and retain recipient, capture/proof reference
and exit state without exposing private payloads in general logs. Follow existing
typed error/result conventions; do not add a generic transaction framework.

Use a Home-to-Home `NONSPENDING_STATE_CHANGE` workflow. Extend `WorkflowContext`
and the canonical navigation/action owner only with the constrained operations
this flow needs. No raw executor, workflow-local OCR, clipboard automation or
fixed-coordinate route is allowed. Mail/Login owns the named Mail methods and
their feature partitions in shared modules; leave generic OCR, guard, runtime,
lease and recovery engines unchanged unless a concrete cross-cutting defect
requires one focused consultation.

Execution order and observable acceptance:

1. Validate `SendMailParams` before connection, prove fresh exact active identity,
   and navigate the requested existing route. Resolve a profile recipient only
   from the qualified current profile; compare it to any explicit requested name
   and kingdom before enabling a player send. A missing kingdom remains a
   contract decision, not a reason to select a similarly named row.
2. Collect the smallest supported pre-send mailbox/thread baseline needed to
   distinguish a new matching message. Reuse canonical Mail observation and
   matching helpers; do not perform an unbounded archive scan. When no trustworthy
   baseline or equivalent correlation is available, report that limitation before
   enabling a success claim.
3. Open Compose, verify recipient/kind, enter only the approved fields through the
   canonical text action and re-observe their current values before Send. Replace
   field contents rather than appending to an old draft. Where a field is not
   observable, obtain the producer contract rather than assuming text entry worked.
4. Dispatch Send at most once from a fresh CLEAR Compose with its exact Send
   control. A transport error or timeout after dispatch is an uncertain send.
   Keep that disposition and never restart the workflow/legacy send phase
   automatically. Ordinary caller retries must not turn uncertainty into a resend.
5. Follow only reviewed known post-send transitions. Reopen the correct mailbox
   and candidate thread if necessary and correlate the new evidence to recipient
   and payload. Reuse current bounded observation/settle ownership. Generic UNKNOWN
   replans and the old repeated compose/send loop do not carry into the port.
6. Confirm Home with the canonical return owner. If sending is confirmed but
   cleanup fails, preserve both facts; do not resend to obtain a cleaner exit.

Keep the no-replay guarantee proportional to the existing send architecture:
one dispatch per invocation, explicit uncertain result, no automatic legacy or
runner retry. This package does not promise durable cross-process deduplication
unless the existing caller contract already requires it. Do not insert Mail into
the Daily journal or claim that restarting a script is safe after an uncertain send.

## M3 — Migrate the real Mail callers and retire only obsolete paths

Bind direct `AutomationSession`/API/module functions, convenience alliance/profile
helpers and authored `TaskId.SEND_MAIL` to the same typed composition. The direct
path owns one reservation and cleanup; authored dispatch borrows the outer
connected runtime. Validate archive dependencies only if actually needed for the
send proof; collecting mail should not become mandatory incidental work.

Replace the old SendMailTask registry path after its supported contract has moved.
Preserve parameter parsing and public routing parity. Remove only obsolete
Send-Mail-specific action/replan paths, with `rg` evidence that no public caller
still bypasses the new boundary. Unqualified original routes remain explicit
unsupported outcomes with open plan items, rather than hidden legacy fallback.

Acceptance: direct and authored sends have the same target/receipt/no-replay
semantics and typed output, and no caller promotes Compose closure to success.
Mail/Login owns its named `TaskId.SEND_MAIL` registry/dispatcher/API/session/module
bindings and feature tests. `TaskId.SELECT_CASTLE`, roster scanning and synthetic
optional-task alignment remain package 06's unchanged semantics; Mail/Login may
consume the active identity they provide but does not add a second scanner or
selection path. The final integrated core gate is outside this package.

## L1 — Specify the actual Login contract before changing credentials flow

After the user supplies the method, produce a small route table from saved/source
evidence: current screen, required identity/content, one permitted action,
next supported screen and terminal success/blocked condition. Include only that
method, already-signed-in verification and the current account-switch continuation
path if it is actually applicable. Do not map the captured email-only form onto
legacy password selectors.

Define separate result evidence for:

- Game is ready on a known surface (`gameReady`), which is not account identity.
- An active character is reachable through fresh roster/Lord information.
- The expected configured account is verified through the supported current
  identity evidence for this method.

Inspect `verified_pnc_account_id`, `current_pnc_account_id`, current-castle
provenance and roster evidence ownership. A failed identity comparison must not be
overridden by a generic Home/Lord Info success branch. Do not infer that a credential
submission succeeded merely because the prior screen was Login. Cached rosters
may support comparison but cannot replace a fresh account/selected-character fact.
If the product only needs an accessible existing session for one caller, name
that narrower result explicitly instead of claiming account authentication.

Producer gate: Mail/Login must qualify the actual native/provider screen
identities, fields and safe controls, loading/overlays, and the evidence needed
for expected account verification. Raw account captures 0199–0202 remain ignored
and private. They cannot become portable fixtures until sanitized without
invalidating the assertion. This package owns the Login-specific models/IDs,
bounded OCR/anchors, fixtures and both observer-path publication needed for this
route; generic vision engines remain outside its scope.

Acceptance: the intended provider contract and success evidence are concrete,
secrets remain in the existing secure configuration path, and missing producer or
operator requirements are named before any logout or submission.
The current native screen's email field and Log In are the only captured
provider controls; username, password and Continue selectors from the legacy
task cannot be assumed. The chosen method is still pending, so no credential
entry, credential request in chat, or login submission may be planned from this
snapshot.

## L2 — Port Login through the existing lifecycle owner

Extend the canonical lifecycle dispatch/composition rather than forcing Login
through a Home-entry workflow that calls active-castle preflight before the user
is authenticated. `CoreScriptDispatcher` already treats Ensure Game Running and
Popup Recovery as lifecycle steps without castle preflight. Reuse that ownership
for the necessary typed Login step, with a dedicated typed result if required.

Keep startup/readiness in its current owner. Login consumes the ready known
surface, performs only its supported account actions through constrained canonical
input, then acquires fresh account/character evidence and returns Home. Once
authenticated, existing castle preflight/selection belongs to package 06; Login
must not introduce a second roster scanner or select an arbitrary castle.

The before-login path must support a logged-out known screen without a circular
identity prerequisite. The after-login path must require the appropriate identity
proof before success. Reuse explicit loading-only bounded settle; UNKNOWN is not
a generic retry state. Wrong account, unknown provider, blocked overlay,
unresponsive control or exhausted deadline stops without repeated credential
submission, account creation, rebinding or fallback to the old engine.

Use current sensitive text-entry/redaction conventions and verify their logs and
artifacts. Do not add raw credentials to params, traces, screenshots promoted to
Git, shell commands, exceptions or agent messages. A provider-specific user step
can return a truthful operator-required disposition; it does not count as a fully
automated login proof.

Acceptance: bounded lifecycle handles a supported known logged-out route and an
already-signed-in route without circular preflight or false account success.

## L3 — Migrate Login/preparation callers without changing castle selection

Update default `TaskId.LOGIN`, authored dispatch, direct/session preparation
helpers and generated `_prepare_account_session_steps` to use the typed lifecycle.
Preserve the intentional ordering: game readiness, account/session verification,
then explicit castle selection where requested. Mail/Login owns the Login branch and
`_prepare_account_session_steps`; `TaskId.SELECT_CASTLE`, roster identity and
synthetic optional-task alignment retain package 06's unchanged semantics. Do not
add a second roster scanner or selection path, and do not wait for or jointly edit
package 06's implementation.

Validate unsupported provider/missing configuration before attempting the dependent
action. Do not force credential availability for a valid already-signed-in proof
unless that public caller specifically promises reauthentication. Remove the old
Login replan/credential fallback only once all intended preparation callers route
to the same supported typed contract. Keep other task families untouched.

Acceptance: generated preparation and explicit Login no longer take different
identity shortcuts, no task reports success on an arbitrary non-Login screen,
and connection/cleanup remains outer-owned.

## Offline validation, separated by behavior

Mail anchors: `tests/unit/app/automation/tasks/test_send_mail_confirmation.py`,
`test_send_mail_failure_paths.py`, `test_send_mail_recovery.py` in that directory;
canonical parameter/API tests; typed core workflow and script dispatch contracts.
Retain meaningful old cases while replacing legacy retry expectations.

Before accepting the Mail consumer, replay the saved Compose fixtures through
both actual observer paths (`ObservationBuilder` and `NavigationPerception`) with
actual RapidOCR and normal bounded semantic requests. A passing producer group
containing injected-OCR tests alone is not that replay. Assert independent Compose identity, requested-only
recipient/subject/body interiors, exact body spacing/punctuation, fresh Send
control and guard provenance. Keep this as an offline no-send replay; it cannot
stand in for a live receipt or for the pending recipient kind/name/kingdom and
subject/body decision.

Required Mail cases:

- Canonical player, alliance and four profile-route parameter contracts;
  malformed combinations rejected before connection.
- Wrong/stale recipient, wrong mailbox kind, altered draft, unsupported field,
  overlay and stale/label-only Send control prevent input.
- Same subject/first line already in the mailbox, another recipient with matching
  text, empty mailbox and ambiguous thread do not prove a new send.
- Positive new correlated receipt, explicit progress/level gate and uncertain
  post-send outcome; each invocation has zero or one Send, never a resend after
  timeout, wrong destination or exit failure.
- Direct/authored/helper parity, typed result provenance and borrowed versus
  owned cleanup. Existing collect-mail/archive behavior remains unaffected.

Login anchors: `tests/unit/app/automation/tasks/test_login_navigation.py`,
`test_login_identity.py`, `tests/integration/vision/test_login_observation.py`,
`tests/integration/script_runner/test_typed_core_dispatch.py`,
`test_castle_target_preparation.py` in that directory, and runner/API preparation
tests. Mail/Login owns recognition and consumer test changes for its named
profiles, fields, lifecycle and callers; generic vision-engine tests and
SELECT_CASTLE/roster implementation tests remain outside this package.

Required Login cases:

- Already-signed-in correct and wrong-account observations; an accessible
  character does not manufacture expected-account proof.
- Supported logged-out route can enter without Home/castle preflight; required
  current identity is verified after authentication before success.
- Captured email-only route is not treated as password/Continue; unsupported
  provider and missing required config are explicit failures/operator requirements.
- Loading settles only within canonical budgets; UNKNOWN, wrong-account return,
  blocking overlay and credential submission uncertainty cause no generic retry.
- Sensitive input does not appear in captured logs/exceptions/results. Use dummy
  values in deterministic tests, never local account secrets.
- Typed generated preparation orders lifecycle before an explicitly requested
  castle selection and neither reconnects nor closes the borrowed runtime.

Run the narrow new producer/workflow contract groups as documented when adding
them, then the repository affected selection for this package. Example commands:

```powershell
& 'C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe' tools/run_tests.py group unit.app.automation.tasks
# Record the actual RapidOCR both-path replay separately from controlled-parser
# tests when Mail/Login producer fixtures or models change.
& 'C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe' tools/run_tests.py group integration.vision
& 'C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe' tools/run_tests.py group integration.script_runner
& 'C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe' tools/run_tests.py group api
& 'C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe' tools/run_tests.py affected --base origin/main --explain --json .test-impact/mail-login-selection.json --results .test-impact/mail-login-results.json
git diff --check
```

Let `affected` require its full fallback for shared/public contracts when necessary;
do not duplicate a passing final gate. Record actual counts/skips/failures on the
new code, not historical results from another revision.

## Live proof M — One approved, correlated Mail send

Run after Mail producer/consumer checks pass and the user supplies the exact
recipient kind/name/kingdom and payload. This package asks the user directly for
that already-pending choice; do not invent a test audience or alter approved text.
Resolve the current assignment's authorized account/instance and configured live
role. Hold the process-scoped canonical lease across all dependent steps and use the
active castle. Prefer one approved player send as the representative send proof;
only add an alliance send if its materially different boundary requires live
acceptance and the user supplies its audience/message. Do not send once per API.

Capture exact identity, recipient, relevant current baseline and Compose fields.
Invoke the migrated production caller, send once, collect the correlated receipt
and return Home. A unique user-approved test payload simplifies proof but cannot
be inserted without approval. A receipt is not currently proven by the saved
Compose checkpoint, so the live run must retain the pre-send baseline and correlate
a new recipient-matching message. If the action's result is uncertain, stop and
inspect existing evidence; do not repeat Send. Do not clear Campaign progress or
change the recipient to evade an observed gate. Record that applicability
condition.

Save nonsecret target/revision/action metadata, raw private frames in ignored
storage, redacted observation diagnostics, one-dispatch trace, correlation result,
pre-send baseline, final Home/stop frame, `summary.json`, `stop.json` and
`cleanup.json`, plus the lease/cleanup disposition under
`.local-data/artifacts/core_ports/mail_send/<run-id>/`. A closed Compose is not a
passed proof. Do not use desktop mouse/keyboard automation or a direct game
service. If the BlueStacks API is unresponsive, stop with the last screen and
failure predicate and ask the user for the needed manual manipulation if it is
necessary to continue. Manual recovery is not production-route acceptance;
a provider-specific user interaction must use the approved
secure channel and does not itself create a send receipt.

## Live proof L — The specified Login method, independently accepted

First validate the existing-session path using the migrated production preparation
caller on the assigned account, its exact observed identity and final Home. This is
useful acceptance for session verification but is not proof of a fresh login.

For the actual Login transition, use one controlled session on the same named
account after the intended method, recovery path and required credential/operator
step are established. Acquire/retain the canonical lease. Reach the supported
login/provider surface through the canonical API, execute one submission/continue
increment, and observe the expected-account evidence and Home. Existing configured
credentials remain local. If a provider requires an email link/code/MFA, request
that precise user action; do not read private inboxes or search for credentials.

Do not log out repeatedly for parity tests or switch to another account to create
a scenario. Missing native recognition or an unresponsive API is a blocked live
boundary; do not use desktop mouse/keyboard control or a workflow-local selector.
A provider-required user step may establish route evidence through its approved
secure channel; record which part remains unautomated and never put credentials
in chat or artifacts. Save redacted before/after observations, action count,
proof strength, last screen, `summary.json`, `stop.json`, `cleanup.json` and
cleanup result under `.local-data/artifacts/core_ports/login/<run-id>/`.

## Completion and self-contained definitions of done

Report Mail and Login separately as implemented/offline passed/live passed or
blocked, with exact remaining route/producer/user decision. Package completion
requires both component definitions below plus one reviewable change from the
recorded current code base. A blocked producer, missing user input or unavailable live
boundary is not Done.

Mail is Done only when the supported original player/alliance/profile routes use
the feature-owned producer models/IDs, bounded OCR/anchors, fixtures and both
observer-path publication; one typed compose/send/verify workflow; direct,
authored and helper parity; strict target/field/current-identity checks; exactly
zero or one Send dispatch with an explicit uncertain disposition; meaningful
before/after recipient-correlated receipt; canonical Home exit; focused offline
checks; the actual RapidOCR both-path no-send replay; and one approved live send
on the assigned account when the user has supplied the exact recipient and
payload. A Compose close, toast or old matching thread is not a receipt.

Login is Done only when the specified provider method has feature-owned screen and
control models, bounded OCR/anchors, fixtures and both observer-path publication;
typed lifecycle behavior for logged-out and already-signed-in routes; truthful
readiness, active-character and expected-account evidence; sensitive input
redaction; no generic retry or credential resubmission; direct/authored/generated
preparation parity through `_prepare_account_session_steps`; unchanged
`SELECT_CASTLE` semantics after authentication; focused offline checks; and the
controlled same-account live proof when the user has supplied the method and any
required secure operator step. Existing-session verification does not close fresh
authentication.

The overall package is Done only when both component results are reported
separately with exact changed files, validation counts/skips/failures, live
artifacts and remaining route/producer/user decisions. Final combined merge or
integration is outside this package and is not a prerequisite for its own
reviewable completion.

## Copyable worker kickoff

> Implement the revised package 05 with PNC_CORE_REMAINING_VISION_BOUNDARY.md.
> Preserve resumed work and record actual code/plan revisions. Reuse V01 shared
> visual/observation machinery and any V-owned surface traversed by a route;
> do not redo their engines, menus or navigation. Own the still-uncovered Mail
> profile/Compose/receipt and specified Login/provider screens, feature-local
> parsers and both-path qualification, typed workflows, callers and lifecycle.
> Preserve one-send/uncertain-result behavior, exact recipient/fields, correlated
> new-message proof and truthful account evidence. Obtain missing recipient,
> payload or Login-method input only when not already supplied; never invent it
> or expose credentials. Use the current execution target/authority, not historical
> allocations. Keep package 06's selection/scanner semantics unchanged. Report
> Mail and Login acceptance separately, tests, artifacts and exact remaining gaps.
