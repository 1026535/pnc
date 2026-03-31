# Scheduled Mail Review Findings

Reviewed commit: `15ad34863befddb8d32b1c31dcffa60a26eb59a7` (`Complete PNC_SCHEDULED_MAIL_IMPLEMENTATION.md`)

## Summary

- 2 high-severity issues
- 2 medium-severity issues
- The new scheduled-mail tests currently pass: `py -3 -m unittest tests.test_scheduled_mail tests.test_script_runner`

## Findings

### 1. High: the documented UTC-only contract is not actually enforced

Affected code:

- `pnc_automation/app/authoring/mail/loader.py:124-139`
- `pnc_automation/app/authoring/mail/loader.py:372-400`

Problem:

- Both `resolve_scheduled_hour_bucket(...)` and `_load_utc_datetime_value(...)` call `.astimezone(UTC)` and only then check `utcoffset()`.
- After conversion, the offset is always `+00:00`, so non-UTC values are silently accepted and normalized instead of being rejected.
- That directly contradicts the implementation document and the CLI contract, which both say these values must already be UTC.
- It also creates inconsistent behavior across surfaces: `cli.py` rejects non-UTC `--scheduled-for-utc`, but the Python/runtime path and YAML loader currently accept it.

Concrete impact:

- `scheduled_for_utc=datetime.fromisoformat("2026-03-31T05:30:00+02:00")` is accepted and normalized to `2026-03-31T03:00:00+00:00`.
- `rotation.start_utc: 2026-03-30T05:00:00+05:00` is also accepted and normalized to Monday midnight UTC.
- That can shift the resolved execution hour/day and make authored schedules fire at times the operator did not intend.

Clean fix:

- Introduce one canonical helper that validates the original value has `utcoffset() == timedelta(0)` before any UTC normalization.
- Reuse that helper from both `resolve_scheduled_hour_bucket(...)` and `_load_utc_datetime_value(...)`.
- Keep the truncation-to-hour behavior after validation.
- Add regression tests covering both API/runtime calls with non-zero offsets and YAML `rotation.start_utc` values with non-zero offsets.

### 2. High: `run_mail_schedules()` returns success for unknown accounts when nothing is due

Affected code:

- `pnc_automation/app/automation/engine/script_runner.py:119-146`
- `pnc_automation/app/automation/engine/script_runner.py:68-81`

Problem:

- `run_mail_schedules(...)` only validates the account indirectly through `run_script(...)`.
- In the no-op branch (`if not due_mail_definitions`), it returns a fabricated `RunResult` immediately and never calls `self.config.require_account(account_id)`.
- That means `run-mail-schedules --account typoed_account` succeeds during an empty hour and only starts failing later when schedules are actually due.

Concrete impact:

- Operator/account-id mistakes can be hidden for days if no scheduled mail happens to be due during testing.
- The behavior is inconsistent with the rest of the entry points, which fail fast on an unknown account.

Clean fix:

- Validate the account at the start of `ScriptRunner.run_mail_schedules(...)`, before due-resolution and before the no-op return path.
- Prefer resolving the `AccountConfig` once and using that canonical object in both the no-op and execution branches.
- Add a regression test that calls `run_mail_schedules(...)` with an unknown account during an empty hour and asserts that it fails.

### 3. Medium: the rotation becomes active retroactively before `rotation.start_utc`

Affected code:

- `pnc_automation/app/authoring/mail/loader.py:72`
- `pnc_automation/app/authoring/mail/loader.py:307-311`

Problem:

- `_resolve_current_day_index(...)` uses modulo arithmetic directly on `(scheduled_hour - start_utc) // 1 day`.
- When `scheduled_hour < start_utc`, the elapsed day count is negative and `% 14` wraps it into `13..0`.
- That makes the schedule effectively active before the authored start anchor.

Concrete impact:

- With `start_utc = 2026-03-30T00:00:00Z`, a schedule authored for `day_indices: [13]` and `hour_utc: 23` is considered due on `2026-03-29T23:00:00Z`.
- If `start_utc` is meant to be the rollout/go-live anchor, the current implementation can dispatch mail before that go-live point.

Clean fix:

- Explicitly treat `scheduled_hour < start_utc` as "nothing due yet" and return no mail definitions.
- If backward replay is ever desirable, make it an explicit opt-in mode rather than the default modulo behavior.
- Add a regression test covering the hour immediately before `rotation.start_utc`.

### 4. Medium: optional scheduled-mail files currently block unrelated commands

Affected code:

- `pnc_automation/app/authoring/config/loader.py:66-75`
- `pnc_automation/app/authoring/config/loader.py:351-366`
- `pnc_automation/app/authoring/config/models.py:206-215`

Problem:

- `load_app_config(...)` eagerly loads and validates the scheduled-mail catalog for every application startup.
- A malformed optional `mail_definitions.yaml` or `mail_schedules.yaml` therefore breaks unrelated commands like `login`, `run`, or `build`, even when scheduled mail is not being invoked.
- That is broader than the implementation document's intended behavior, which framed scheduled-mail validation as a requirement of the scheduled-mail surface itself.

Concrete impact:

- A typo in optional scheduled-mail authoring can take down the entire CLI/API surface instead of only the scheduled-mail entry point.
- This increases operational blast radius for a feature that is supposed to be optional.

Clean fix:

- Keep `mail_definitions_path` and `mail_schedules_path` on `AppConfig`, but lazy-load the catalog the first time `require_mail_schedule_catalog()` is called.
- Cache the loaded catalog after the first successful read.
- Keep the same fail-fast validation rules, but apply them only when scheduled-mail functionality is actually used.
- Add tests proving unrelated commands still boot when scheduled-mail files are absent or malformed, while `run_mail_schedules(...)` still fails fast.

## Low-Risk Cleanup Opportunities

- Centralize generated schedule naming/stamp creation. The `generated_mail_schedule_%Y%m%dT%H0000Z` format is currently duplicated between `build_generated_send_mail_script(...)` and `_generated_mail_schedule_name(...)`.
- Avoid re-normalizing `scheduled_for_utc` multiple times in the same execution path. It is normalized in `ScriptRunner.run_mail_schedules(...)`, `resolve_due_mail_definitions(...)`, and `build_generated_send_mail_script(...)`.
- Add lightweight provenance for generated scheduled-mail steps, such as `mail_id` and `schedule_id`, so failures are easier to trace back to the authored source.
