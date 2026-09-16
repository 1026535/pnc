# Keepalive and Python monitoring

Create or reuse one native `automation_update` heartbeat in the current task, preserving its ID, target, and notification preferences. Set its name to `Devin cache keepalive`, interval to 27 minutes, and status active. Replace the older health-check prompt with exactly: `Cache keepalive only. Do not call tools, inspect worker progress, or produce commentary. Return an empty final response.` Use the tool for initial setup; never edit automation files manually.

Start one Python monitor in an ignored directory, supplying the existing automation ID. It uses the existing native app-tools MCP bridge for subsequent timer updates; no alternate scheduler or additional model is involved. It runs hidden, tails newly appended lifecycle records from the verified lead rollout, and checks registered workers every 15 minutes. Startup requires an acknowledged active timer. An OS lock prevents two monitors for the same lead, even across monitor directories.

```powershell
$devinMonitorDirectory = Join-Path $PWD '.local-data/devin-monitor'
python "$devinSkill/scripts/devin_monitor.py" start --monitor-dir $devinMonitorDirectory --thread-id $env:CODEX_THREAD_ID --automation-id <existing-heartbeat-id> --run-dir $devinRunDirectory
# Register another worker without starting another monitor:
python "$devinSkill/scripts/devin_monitor.py" register --monitor-dir $devinMonitorDirectory --run-dir <absolute-run-directory>
# On demand, to diagnose the monitor itself:
python "$devinSkill/scripts/devin_monitor.py" status --monitor-dir $devinMonitorDirectory
# At acceptance or explicit stop; wait for shutdown and confirm the timer is paused:
python "$devinSkill/scripts/devin_monitor.py" stop --monitor-dir $devinMonitorDirectory
```

A keepalive wake returns an empty final response with zero lead tools, questions, status reads, or commentary. Python observes `event_msg` / `task_complete` with its turn ID and resets the same heartbeat afterward, normally within two seconds plus native bridge latency. Any other completed lead turn also resets it; a newer active turn defers resetting until completion. Cursor persistence, partial-line handling, and completion deduplication avoid historical replay. This replaces the previous lead-side pre-return update: an after-completion reset removes the extra model request required to consume a tool result. Stop requests take precedence over in-flight rearming. Timer failures retry with bounded backoff and issue one alert after three consecutive failures; fatal monitor errors persist evidence and attempt one actionable notification.

The monitor compares tool-event timestamps and identity/stdout byte growth, excluding the supervisor's own heartbeat from progress. Repeating the same tool name with new events counts as activity. A dead supervisor or heartbeat older than two minutes is actionable at the next sample. Two full 15-minute intervals with unchanged activity and no outstanding tool produce a possible-inactivity alert; a live outstanding tool remains quiet. These checks cannot prove semantic progress or distinguish every stall from legitimate computation. They never cancel or resume a worker automatically. An anomaly is latched until activity/health changes to prevent repeated lead wakes.

Completion delivery records distinguish confirmed failure from uncertain acknowledgement. After a two-minute grace, Python retries only a conclusively undelivered callback, at most once per health interval; it does not resend a possibly delivered message. Old ambiguous or missing notification records require on-demand reconciliation. Failed anomaly delivery remains in monitor evidence for recovery. No mechanism guarantees delivery when the app or monitor is down. After restarting Codex or its app-tools pipe, stop/restart this monitor with the current environment and the same directory/ID; inspect `state.json` and `stderr.log` if startup fails. `stop` can recover a paused timer even when the monitor has died. The computer must remain awake and Codex running.

This relies on locally verified rollout metadata and the bundled app-tools connection, not a public cache-control API; revalidate after relevant Codex changes. The [official prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching) documents prefix reuse and model-dependent retention, but does not guarantee this Codex keepalive method. A 27-minute timer leaves nominal margin against a 30-minute retention window; delays, routing, prefix changes, or different retention settings can still miss. Each keepalive still processes the lead's applicable context. One empty response is a target, not a proven guarantee of fewer than 5,000 total tokens, under 5% allowance, or zero cost. Measure actual request count, cached/uncached input, and output in a later live run; do not infer subscription cost from raw token totals.

## On-demand progress

Use plain `devin_worker.py status` once for the relevant worker, then the native `/btw` side question documented in [runtime.md](runtime.md#side-questions-through-the-owned-connection) when transport is healthy and an answer would help. Neither runs on a scheduled keepalive.

Treat the answer as self-report. When an answer is missing, contradictory, or repetitive, choose either `status --recent` or the specific relevant test failure, diff, or log excerpt (up to 4,000 characters). Do not automatically read both or restart a worker to obtain an answer. `status --recent` contains up to eight hook events (400-character input/error excerpts), 2 KiB stdout and 1 KiB stderr tails. These bounds limit new evidence, not existing context processed by every lead request, and are not total token or billing ceilings. Inspect unhealthy transport directly; after confirmed failure, reconcile writer/resource ownership before resuming preserved work.

## Validation

On 2026-09-14, all 45 offline worker/ACP/monitor tests passed, including incremental completion handling, duplicate suppression, same-name tool activity, long-running tools, callback ambiguity, retry backoff, exclusive monitor ownership, and stop/rearm races. Run them with `python -m unittest discover -s "$devinSkill/scripts" -p 'test_devin*.py'`. A native Windows smoke test confirmed hidden monitor startup, an acknowledged active heartbeat update through the shared MCP bridge, and shutdown with a paused acknowledgement. Completion-triggered rearming was tested with synthetic lifecycle records. Actual scheduled empty responses, cache reuse, and usage savings have not yet been benchmarked.
