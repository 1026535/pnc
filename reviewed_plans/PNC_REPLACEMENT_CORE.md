# Replacement navigation core — implementation record

Branch: `codex/pnc-replacement-core`. Created from the existing checkout with pre-existing working-tree changes preserved. This record describes the replacement-core changes, not ownership of the entire working tree.

## Implemented architecture

The opt-in core reuses the configured BlueStacks session, screenshot storage, image matcher, domain models and device actuator. It runs independently of the legacy observation-builder/classifier/flow/retry loop. Unsupported states do not fall back to that loop during a core transition.

Live accessibility reconnaissance found six Android nodes, zero text nodes and zero clickable nodes on the active city screen. That inspected hierarchy did not expose usable game controls, so this implementation uses image evidence.

| Responsibility | Core behavior |
|---|---|
| Screen identity | Global visual profiles, independent of the requested destination or OCR content family |
| Overlay ownership | Explicit containment; More can own the still-visible City/World background; unrelated conflicting matches abstain |
| Control targeting | A current-frame template match; inferred registry geometry cannot authorize navigation |
| Modal ownership | A recognized dialog owns its measured Close control; update/disconnect text guards still run independently |
| Content | Optional parsing after identity; contradictions fail, and parsed content cannot create navigation controls |
| City objects | Unique observed object and current tap point; no atlas, remembered camera position, or blind scanning |
| Routing | Reviewed non-spending graph, replanned after each confirmed transition |
| Completion | One action, bounded passive observations, two consecutive fresh destination captures |
| Failure | Recorded evidence and stop; no repeated tap or automatic popup recovery |

There is one completion implementation for template controls and observed city objects. The visual catalog and matcher are extended in place rather than copied. Existing content and global interruption parsers remain shared during migration.

## Files

- `pnc_automation/app/automation/engine/navigation_core.py`: typed graph, routing, completion and observed building entry.
- `pnc_automation/app/pnc/vision/navigation_perception.py`: independent identity, guard and optional content extraction.
- `pnc_automation/app/pnc/vision/visual_screen_recognizer.py`, `data/screen_anchors.json` and PNGs: measured controls, modal/overlay ownership and five additional screen profiles.
- `pnc_automation/app/pnc/vision/pnc_observation_enricher.py`: separate interruption API using existing popup/loading parsers.
- Screen/selector enums and `selector_registry.yaml`: expanded-world state and a distinct HUD toggle with explicit outcomes.
- `tools/validate_visual_navigation.py`: opt-in `--replacement-core` proof using the configured runtime.
- `tests/test_navigation_core.py` and `tests/data/screen_recognition/`: targeting, transition, modal, content and animation regressions; asset provenance in `replacement_core_provenance.json`.

## Live-derived corrections

1. An initial city anchor included the animated Z above Build. The first attempt stopped before tapping. It now uses the stable Build label, and the failed frame is a regression fixture.
2. A legacy upgrade-warning color heuristic misidentified the coordinate dialog. This workflow-specific heuristic is not used as a general core guard.
3. The coordinate dialog's own gold X triggered generic popup detection. Measured modal ownership now resolves that case while preserving independent update-text detection; an offline regression checks both behaviors.
4. An initial control crop confused the four-arrow HUD toggle with the separate kingdom-overview entry. The failed live frame supplied the expanded-world state and its return control. The overview crop was corrected. The core subsequently proved Expanded World to World to City.
5. The old identity probe's allowlist lacked the known dialog/overview Close and World Home controls. Those non-spending return controls were added.

Failed attempts remain under `artifacts/replacement_core/live/`; they are not successful route evidence.

## Verification

```powershell
py tools/validate_visual_navigation.py --replacement-core --account testing --output-dir artifacts/replacement_core/live
```

The core first returns from a supported starting map/modal to City. The retained legacy identity preflight then inspects the active castle without selecting another one. All subsequent core captures and transitions use independent perception and completion. No purchases, reward claims, resource use, research start, recruitment, dispatch, messages or castle switching are included.

- Focused navigation/recognizer/probe/selector/discovery checks: passed, 49 tests, `artifacts/replacement_core/focused.log`.
- Earlier recognition checks exposed three More/root overlap failures, corrected with explicit containment.
- An intermediate full run failed with 62 catalog-load errors because the HUD-toggle declaration omitted reviewed outcomes. The declaration was corrected and focused checks passed. This was an integration error in the replacement work.
- `py -m unittest discover -s tests`: passed, 1,041 tests, 17 skips (`artifacts/replacement_core/unittest_final.log`).
- Final live tour: pending completion.

## Migration boundary

This is a bounded replacement navigation core, not a completed rewrite of all bot workflows or a complete map of the game. It is opt-in; the default daily-maintenance runner remains unchanged by the core migration.

The graph covers City, World, expanded World, coordinate dialog, kingdom overview, Quest Main/Daily, Bag, More, Settings and Institute. Observed city-object entry requires a recognized destination and reviewed return route; the live proof targets Goddess Statue. Invisible or ambiguous buildings produce a no-action failure. Measured camera search/localization, broader screens, other languages/layouts, spending workflows and interruption-recovery policies remain outside this first core.

Same-session captures are correlated. New reference images and failure-derived regression frames are not independent holdouts. Small live tours do not establish unattended reliability. The global OCR guard is retained, so this implementation is not claimed to solve perception latency yet.
