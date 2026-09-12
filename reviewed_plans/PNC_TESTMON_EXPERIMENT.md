# Synthetic pytest/testmon experiment

This is an isolated synthetic fault experiment, not an audit of historical PNC changes. The adoption gate is **not established**. Whole-PNC parity, historical recall, and meaningful iteration-time savings require separate evidence.

Completed **34** independent mutations. Versions: pytest 9.0.2, coverage 7.10.7, pytest-testmon 2.2.0.

Every case starts in a new directory, runs a clean full unittest baseline, seeds testmon from the same unchanged fixture with `--testmon --testmon-noselect`, verifies identical IDs, applies one mutation, and checks exact failing IDs with independent full unittest before running raw affected testmon. Native selection also executes its selected unittest modules. Every subprocess blocks network auditing events and disables pytest plugin autoload; only the installed testmon plugin is explicitly loaded. No PNC runtime, account config, or live fixture is used. No global configuration is changed.

Raw testmon misses: **13 cases**; native misses: **0 cases**; raw testmon tool errors: **1 cases**. Tool errors are not successful runs.

Of the missed cases, **12** returned exit 0; **0** returned pytest exit 5 (no tests collected), which is nonzero and must not be called green.

Native full-fallback decisions: **28 cases**. The baseline deliberately includes an unresolved dynamic importer, which makes native selection conservatively broad for most Python edits. This comparison measures recall, not native selection precision or PNC iteration speed.

The mandatory guard independently runs architecture/public-contract checks, plus all synthetic resource tests for resource mutations. It bypasses testmon filtering. Missing/corrupt state requires a separate full-run fallback; a guard limited to contracts/resources is not a substitute.

| Mutation | Full failures | Raw selected | Raw missed | Native missed | Guarded missed | Raw exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| private-body | 4 | 4 | 0 | 0 | 0 | 1 |
| public-default | 1 | 5 | 0 | 0 | 0 | 1 |
| public-signature | 2 | 5 | 0 | 0 | 0 | 1 |
| api-body | 1 | 1 | 0 | 0 | 0 | 1 |
| api-default | 1 | 1 | 0 | 0 | 0 | 1 |
| lazy-implementation | 1 | 1 | 0 | 0 | 0 | 1 |
| lazy-export-remap | 1 | 2 | 0 | 0 | 0 | 1 |
| relative-from-symbol | 1 | 1 | 0 | 0 | 0 | 1 |
| dataclass-field | 2 | 2 | 0 | 0 | 0 | 1 |
| class-method | 1 | 1 | 0 | 0 | 0 | 1 |
| decorator-body | 1 | 1 | 0 | 0 | 0 | 1 |
| module-setup | 1 | 1 | 1 | 0 | 1 | 0 |
| class-setup | 1 | 1 | 1 | 0 | 1 | 0 |
| shared-helper | 1 | 1 | 0 | 0 | 0 | 1 |
| test-assertion | 1 | 1 | 0 | 0 | 0 | 1 |
| new-failing-test | 1 | 1 | 0 | 0 | 0 | 1 |
| production-rename | 4 | 5 | 0 | 0 | 0 | 1 |
| production-delete | 1 | 1 | 0 | 0 | 0 | 1 |
| removed-import-edge | 1 | 1 | 0 | 0 | 0 | 1 |
| package-initialization | 1 | 1 | 1 | 0 | 1 | 0 |
| dynamic-plugin | 2 | 2 | 0 | 0 | 0 | 1 |
| exception-contract | 1 | 1 | 0 | 0 | 0 | 1 |
| async-body | 1 | 1 | 0 | 0 | 0 | 1 |
| source-scanned-import | 1 | 0 | 1 | 0 | 0 | 0 |
| source-scanned-symbol | 1 | 0 | 1 | 0 | 0 | 0 |
| static-json | 1 | 0 | 1 | 0 | 0 | 0 |
| static-yaml | 1 | 0 | 1 | 0 | 0 | 0 |
| static-png | 1 | 0 | 1 | 0 | 0 | 0 |
| static-text | 1 | 0 | 1 | 0 | 0 | 0 |
| static-sql | 1 | 0 | 1 | 0 | 0 | 0 |
| static-markdown | 1 | 0 | 1 | 0 | 0 | 0 |
| unknown-binary | 1 | 0 | 1 | 0 | 0 | 0 |
| cache-missing | 4 | 27 | 0 | 0 | 0 | 1 |
| cache-corrupt | 4 | 0 | 4 | 0 | 4 | 3 |

Raw misses in source-as-data: source-scanned-import, source-scanned-symbol.

Raw misses in static-resource: static-json, static-yaml, static-png, static-text, static-sql, static-markdown, unknown-binary.

Raw misses in cache: cache-corrupt.

Architecture/public-contract/resource guards alone still miss: module-setup, class-setup, package-initialization, cache-corrupt. Setup dependencies need explicit owning-module coverage; package initialization and invalid selection state need conservative full fallback. Do not adopt raw testmon plus only architecture/resource guards. The independent full run is the verified failure oracle for every such case.

Initial native misses preserved in JSON before revalidation: static-markdown. The table reports the latest native recheck; the initial native result and original testmon result remain attached to each case.

Median subprocess wall times (tiny fixtures, not PNC performance evidence): full_unittest 0.344s, raw_testmon 1.805s, native_selector 0.217s. Native timing excludes separately recorded planning time; testmon includes its analysis. Baseline seeding and mandatory-guard time are recorded separately in JSON.

Machine-readable results: .test-impact/testmon-experiment/results.json

Rerun from the repository root:

```powershell
.venv/Scripts/python.exe tools/experiment_test_selection.py
```

After a native-selector fix, `--refresh-native` rechecks retained candidate sources and reruns only native selection, preserving the original testmon evidence.

Each run preserves its case fixtures, baseline/affected XML, unittest JSON, subprocess logs, source hashes, seed-cache hashes, exact missed IDs, and native selection reasons under `.test-impact/testmon-experiment/`. Synthetic PNG/binary samples are byte-contract fixtures; no image decoder, OCR, emulator, or external service is exercised.
