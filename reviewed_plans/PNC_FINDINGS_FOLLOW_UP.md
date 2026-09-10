# Findings follow-up — September 10, 2026

## Recognition status

The original findings are not all equivalent to resolved implementation defects.

| Finding | Current disposition |
|---|---|
| Quest-only return-home observation hides Hero Hall | Fixed: return-home uses the canonical full request; visual identity also runs independently of content-family scope. Deterministic regression tests cover non-Quest source screens. |
| Missing template assets | Partially addressed: the new recognizer has 18 packaged anchor images for nine profiles. All 76 effective legacy template/collection paths remain missing under `pnc_automation/templates/pnc`; these selectors still skip template detection. The screen anchors do not complete visual coverage for individual controls. |
| Promising but correlated 657-frame experiment | A separate manually reviewed 18-frame benchmark now exists, with disjoint reference/holdout groups and decoded hashes. Zero wrong actionable classifications on this set is encouraging, not broad production-accuracy proof. |
| More overlay and full Settings shared one screen state | Fixed: separate screen contracts, migrated navigation and selector outcomes, offline isolation checks, and live proof. |
| Overlay controls must take precedence over the background | Implemented and tested, including an undarkened Bag header under an update dialog. OCR popup/loading guards remain required. |
| Android hierarchy lacks useful Settings semantics | Observed platform limitation, not a repository bug. The implementation does not depend on semantic Android controls for Settings. |
| Trained classifier/YOLO comparison | Deferred. No trained PNC detector or same-dataset model comparison has been completed. |
| Durable action trace | New bounded live tool writes unique append-only before/after records; the two implementation runs passed and ended at Home. The original exploration's overwritten trace remains historical. |

## Journal permission investigation

The errors occurred at `DailyRunJournalStore.save()` while replacing an existing `journal.json` with a flushed, closed temporary file. They were not OCR assertions. A 1,000-write native filesystem probe reproduced two `WinError 5` failures; retrying the identical rename after 10 milliseconds recovered both. This establishes transient denial, but does not identify the process or filter responsible. No attribution to antivirus, indexing, or a specific application is proven.

Windows open-handle sharing modes can prevent rename/delete until a handle closes; Microsoft documents that rename requires delete access. See [CreateFile sharing rules](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).

The journal now retries only replacement of the same flushed payload for Windows errors 5, 32, and 33. Seven attempts allow at most 630 milliseconds of scheduled backoff. Other I/O errors propagate immediately; a persistent denial still raises. The old journal is never deleted as a workaround, permissions are not changed, and the retry does not replay a game action. Existing serialization and persist-before-dispatch ordering remain intact.

A second 1,000-write probe using the production retry completed all writes and recovered five real transient errors. These probes used generated local test journals, not account configuration or live game actions. Evidence: `artifacts/recognition_implementation/journal_probe.json` and `journal_probe_after.json`.

`py -m unittest tests.test_daily_run_journal` passed 12 tests, including successful transient recovery, permanent-denial exhaustion, old-content preservation, temporary-file cleanup, immediate disk-error propagation, and no game dispatch when intent persistence fails. The earlier 20-test journal/Hero Hall/resource-item run also passed. This filesystem-only change is exercised directly on Windows; it does not require spending game resources or repeating emulator navigation.

`py -m unittest discover -s tests` passed: 994 tests run, 17 skips, zero failures/errors, in 86.818 seconds. Log: `artifacts/recognition_implementation/journal_full_suite.log`. `git diff --check` passed. No account or castle configuration was changed. The earlier unclean-suite result in the implementation report is superseded by this run.
