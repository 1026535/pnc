# Local runtime

The launcher supports **native Windows, Python 3.11+, Git, and authenticated Devin CLI**. Other operating systems require a different process-lifetime adapter.

## Configuration

The launcher resolves `devin` from PATH or `%LOCALAPPDATA%/devin/cli/bin/devin.exe`, records its version, and checks the account catalog for `swe-2-max`. It verifies exported models, resume identity, and absence of nested subagent tools. If authentication fails, use `devin auth status` and the documented login flow.

The authorized defaults are `--permission-mode dangerous` and `--respect-workspace-trust false`, applied after exact Git-root and HEAD validation. Routine commands need no approval grants. Explicit `normal`/`accept-edits` overrides retain workspace trust and support repeated `--allow-rule` arguments. Native Windows has no Devin filesystem sandbox; host and organization restrictions still apply.

A per-turn config replaces the CLI user config, disables imported tool settings and nested subagents, and sets `attribution: false` so worker commits and PRs omit Devin footers. Shared settings are not modified. The per-turn overlay sets `agent.compaction_threshold_tokens` to 100,000. Four SWE-2 sessions on CLI 3000.10.27 failed around 131–134k context tokens despite the catalog advertising 262k; earlier compaction recovered the exact failed session on September 16 (130,770 → 36,425 reported tokens, successful final response). This is an observed workaround, not a claim about the provider’s undocumented limit. The setting is supported by the [official 3000.10.21 changelog](https://docs.devin.ai/cli/changelog/stable). Project/system rules, hooks, and dedicated MCP configuration can still apply; investigate the specific setting if a conflict occurs.

## Launch independently

Use absolute paths. Set `$devinSkill` to the installed skill folder and run from the exact target Git root. Create the brief first. The fresh run directory must not exist; choose an ignored location and preserve it for resumes.

```powershell
$devinSkill = (Resolve-Path '.agents/skills/devin-implement').Path
$devinRepo = (Get-Location).Path
$devinBaseline = git rev-parse HEAD
$devinRunDirectory = "$devinRepo/TestResults/devin-implement/task-name"
$devinPython = (Get-Command python).Source
$devinLaunchLog = "$devinRunDirectory-launch-$(Get-Date -Format yyyyMMdd-HHmmss)"
[IO.Directory]::CreateDirectory((Split-Path $devinRunDirectory)) | Out-Null
$devinArguments = @(
  "`"$devinSkill/scripts/devin_worker.py`"", 'run',
  '--repo', "`"$devinRepo`"", '--expected-head', $devinBaseline,
  '--run-dir', "`"$devinRunDirectory`"",
  '--brief', "`"$devinRepo/TestResults/task-brief.md`"",
  '--notify-thread', $env:CODEX_THREAD_ID
)
Start-Process -FilePath $devinPython -ArgumentList $devinArguments `
  -WorkingDirectory $devinRepo -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput "$devinLaunchLog.stdout.log" `
  -RedirectStandardError "$devinLaunchLog.stderr.log"
```

This returns the independent supervisor PID and opens a **visible console for Devin's live output**, while retaining stdout/stderr logs. The supervisor itself stays hidden. The contained ACP adapter owns Devin’s connection from launch; this is an output console. Use `ask`, `steer`, and `cancel` through the launcher, without typing into or scraping that console. Closing that console interrupts its worker. Add `--no-console` only when the user explicitly requests no console.

Launcher and ACP adapter output use UTF-8 explicitly, including redirected Windows pipes, so Unicode responses cannot terminate a worker through the host's legacy code page.

Confirm startup produced the expected turn's `state.json`; if missing, inspect the launch stderr and PID before retrying. The launcher has **no task-duration timeout**. The worker may run for hours; ending a Codex turn does not cancel it.

## Completion and monitoring

The supervisor sends one compact native task message for a completion, returned blocker, or failure. The app-tools bridge steers an active lead or wakes an idle one without model inference to construct the message. Handle each run-directory/turn once.

Follow [keepalive.md](keepalive.md) for the 27-minute minimal keepalive, Python timer rearming, 15-minute liveness checks, setup/shutdown, and recovery. Scheduled wakes perform no worker checks or side questions. The same reference owns on-demand diagnostic bounds and cache limitations.

On completion, `turn-NNN/result.json` and `handoff.md` hold the result; logs, exports, prompt/config, and before/after snapshots remain in that turn directory for targeted inspection.

`exited` means the CLI supplied a final response with valid model evidence. A zero exit without a new final response, including observed headless permission rejections, is `incomplete`. The lead evaluates readiness separately. The launcher does not retry automatically.

## Side questions through the owned connection

Use this short progress question on demand for a running worker with healthy transport, after plain `status`. Scheduled keepalives never invoke it. The native side chain reads the current conversation without adding the question/answer to the main chain or redirecting implementation. No worker-maintained progress file is required.

```powershell
python "$devinSkill/scripts/devin_worker.py" ask --run-dir $devinRunDirectory --question "Briefly state your current objective, latest meaningful result, unresolved issue, what you learned, and next action."
# If pending, retrieve the returned ID without resubmitting:
python "$devinSkill/scripts/devin_worker.py" ask --run-dir $devinRunDirectory --request-id <returned-id>
```

The command asks for at most 150 words and returns only that request's answer, at most 2,400 characters, plus small identity/status metadata. Truncation is explicit. A typical answer is several hundred tokens; a filled character allowance with ordinary prose and metadata is roughly 600–1,000 lead-input tokens, plus the plain-status result. These are not hard token limits or total billing estimates. Worker inference can use substantial context; it does not enter the lead's context. The bounded answer limits new evidence, not existing context processing. Treat the answer as self-report, not test evidence.

Waiting defaults to 45 seconds (`--wait-seconds` accepts 0–60); expiry returns `pending` and the request ID, without cancelling either chain. Concurrent questions are serialized because Devin exposes one side chain. Results remain scoped to their request and turn. Failed or unavailable questions are reported explicitly; use the existing bounded evidence check instead of retrying blindly. A main handback can overtake a queued question. An already-running side answer gets at most 60 seconds after main completion before it is cancelled, so it cannot indefinitely delay the completed handback. This does not limit implementation duration.

`scripts/devin_acp.py` uses standard ACP JSON-RPC correlation plus the installed Devin extension: initialize advertises `clientCapabilities._meta["cognition.ai/chains"] = true`; the `/btw` prompt carries `_meta["cognition.ai/chain"] = "side"`; response chunks carry the same tag in `session/update.params._meta`. Untagged updates are main-chain output. Only side `agent_message_chunk` text enters an answer; thoughts, tools, other sessions, history replay and main output are excluded. Main and side prompts have independent request IDs. Never infer routing from timing or text markers.

The adapter runs inside the existing Windows job, using atomic turn-local question/result files; it adds no network endpoint, watcher service, alternate writer, or separate reporter model. Native main-chain tool permission requests receive an `allow_once` response only under the explicitly authorized `dangerous` mode. Narrower modes do not gain automatic grants. Unexpected client operations fail closed. Native forest ancestry establishes model/session/final-response evidence. Freshness uses the current main prompt ID, or an exact match against the live main answer's SHA-256 and byte count when compaction removes that ID. The fingerprint resets at main tools/thoughts and ignores replay/side updates; it stores no transcript. A match also requires native `end_turn`. Side answers cannot become handoffs.

An older print-mode turn has no owned control endpoint. `ask` rejects it; never bypass its session lock or launch a competing connection. It can adopt ACP on its next normal resume after releasing writer/resources. Live compatibility was established with Devin CLI 3000.10.21; extensions are vendor-specific. Revalidate focused protocol behavior after relevant CLI changes rather than silently guessing new fields.

## Live steering

For a resolved correction, send only the changed direction and affected checks. `steer` adds the message to the active main conversation, preserving the session, process, and partial work. It does not interrupt a running tool or replace an inference already producing an answer; Devin can incorporate the correction at its next inference. A final answer already in progress may not reflect it. Use normal evidence/review to assess the result, or `cancel` when work must stop.

```powershell
python "$devinSkill/scripts/devin_worker.py" steer --run-dir $devinRunDirectory --message "Use owner X for this behavior; remove the duplicate helper and run checks A and B."
# If pending, retrieve the same ID without sending another correction:
python "$devinSkill/scripts/devin_worker.py" steer --run-dir $devinRunDirectory --request-id <returned-id>
```

Messages are limited to 2,000 characters. The default five-second wait (`--wait-seconds` accepts 0–60) reads only a small request receipt: `pending`, `sent`, `not_sent`, `uncertain`, or `failed`. `sent` means written to the owned connection, not proven compliance; a native completion adds its stop reason. Receipts omit the message, model output, usage history, and transcript. They require no model acknowledgement, side question, or automatic resend. Retrieve `pending` by ID; resolve `uncertain` or `failed` from the existing result/evidence before deciding whether another instruction is needed.

The adapter rejects undispatched corrections after completion/cancellation as `not_sent`. If native completion races an already-sent correction, it waits for that prompt too; Devin may process it as the next native turn in the same session. No synthetic follow-up is added. Overlapping prompt responses can share cumulative usage and must not be summed. Old adapters without the advertised `steer` control require their normal handback/resume; editing these files does not upgrade an already-running adapter.

## Resume and ownership

Add `--resume` to `$devinArguments` before `Start-Process`, with the same `--run-dir`, the delta brief, and the checkout's current expected HEAD. Use new launch-log paths and preserve any explicit permission override and grants. The launcher resumes the recorded session ID and adds a numbered turn. Exported usage totals are cumulative.

The worker receives one initial implementation brief per launched turn; `steer` supplies explicit deltas and on-demand side questions remain separate. A package handback, including `NEEDS_LEAD`, ends that turn and uses the existing completion callback, without automatic retry. When lead intervention requires interrupting active work, cancel below, reconcile resource ownership, and resume the same session with the resolved direction. Updating skill files or the heartbeat does not change submitted instructions.

`state.json` records execution, not review acceptance. The OS lock excludes concurrent launcher writers in one Git worktree; it cannot coordinate unrelated tools or human edits.

## Cancellation and recovery

For an internal ACP failure, first read `result.json` or plain `status`: it includes the configured compaction threshold and compact live-main context metrics (latest/peak occupancy, advertised window, completed compactions). `context.json` is updated from native events and survives prompt failure; missing metrics mean unavailable, not zero. Counts are per launched turn and exclude session-load replay and side questions. They are context snapshots, not billed token totals or evidence of an upstream limit.

If necessary, inspect one bounded stderr excerpt and the recorded CLI/model identity. An opaque `-32013` does not by itself establish an authentication failure or service outage. Compare against the observed context-boundary failure above, confirm the 100,000-token overlay was applied, and distinguish evidence from hypotheses. Preserve partial work, verify writers and external resources are released, then resume the same session only after a relevant setting, context, code, or state change. Do not repeat an unchanged failed prompt or start parallel diagnostic sessions. If early compaction is already active and the same failure recurs, retain the compact evidence and investigate the specific error; do not keep lowering thresholds or add a generic retry loop.

```powershell
python "$devinSkill/scripts/devin_worker.py" cancel --run-dir $devinRunDirectory
```

`cancel` requests native ACP interruption of main work and any active side question. The adapter stops admitting prompts and permission grants, drains cancellation responses, and closes normally. The supervisor allows 15 seconds after observing the request for native shutdown, then terminates the contained process tree if needed; older adapters without native cancellation support use process cleanup directly. This grace bounds cancellation, not task duration, and adds no model prompt.

Wait for a terminal record and `writers_stopped: true`. Status records whether cancellation was `graceful`, `forced`, or the process exited before native acknowledgement (`process_exit`). Any remaining ordinary descendants are cleaned up before releasing writer ownership; a cancelled response is never accepted as a completed handoff. Source edits and other Devin sessions are preserved. Supervisor death still closes its Windows job, and Python monitoring can flag unhealthy execution for lead recovery.

Existing editors, remote services, and brokered operations are outside that job. Cancel persistent editor or test runs through their canonical command and exact run ID before releasing those resources.

After supervisor interruption, use the retained state, process/job identity, `identity.jsonl`, and relevant logs to reconcile local writers and external tests. Repair a stale `running` record only after that reconciliation. If no export exists, verify the hook-recorded session ID against `devin list --format json` in the exact repository before restoring the resume identity. Preserve partial edits and evidence throughout recovery.

## Capability sources

Verified 2026-09-13 against installed 3000.10.21:

- [CLI commands](https://docs.devin.ai/cli/reference/commands): print/prompt files, explicit resume, exports, model listing, statistics.
- [ACP prompt lifecycle](https://agentclientprotocol.com/protocol/v1/prompt-turn#cancellation): native cancellation and completion acknowledgement. Live main-prompt steering was verified separately against installed Devin 3000.10.21; it is not inferred from generic ACP support.
- [Models](https://docs.devin.ai/cli/models): family aliases can change; use account-resolved variants.
- [Configuration](https://docs.devin.ai/cli/reference/configuration/config-file) and [precedence](https://docs.devin.ai/cli/reference/configuration/global-vs-local): worker overlay and merged policy.
- [Lifecycle hooks](https://docs.devin.ai/cli/extensibility/hooks/lifecycle-hooks): native session/prompt identity and bounded tool activity; hooks do not request continuation or modify tool decisions.
- [Codex scheduled tasks](https://learn.chatgpt.com/docs/automations#schedule-a-task-inside-a-chat): minute-based follow-ups retaining the current task's context.
- [Permissions](https://docs.devin.ai/cli/reference/permissions): unattended editing versus execution.
- [Windows job objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects): descendant lifetime and its limits.
