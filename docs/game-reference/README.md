# PNC game behavior reference

Use this reference to check assumptions, identify meaningful postconditions, and locate client behavior while implementing or reviewing PNC automation. It is research evidence, not a second runtime or a standalone game client.

## Coverage

The packaged PNC **5.0.203 / version code 233** yielded **6,276 gameplay Lua files**, including **459 files under `commands/`**. This gives broad source discovery across the client. It does not mean every workflow has been analyzed, nor that downloaded updates match the APK.

| Reference | Coverage status |
|---|---|
| [Source map](SOURCE_MAP.md) | Discovery across the recovered source; individual workflows mostly unverified |
| [Shared request path](REQUEST_PATH.md) | Native outgoing path statically traced; checksum independently checked by isolated emulation |
| [Building upgrades](workflows/building-upgrade.md) | Normal-upgrade UI checks, request, response handling, and automation implications inspected |
| [Castle skins and ambience](workflows/castle-appearance.md) | Castle and ambience preview layers, world-map rendering, and appearance-collection implications |
| [Campaign navigation](workflows/campaign-navigation.md) | Chapter 10 and stage 10-3 saved transitions, source correspondence, and bounded automation implications |
| [Resource tile labels and markers](workflows/resource-tile-markers.md) | Resource artwork, occupancy, protection, focus markers, and OCR/automation uncertainty |
| [Seasonal Alliance layouts](workflows/seasonal-alliance-layout.md) | Recovered Faction eligibility/layout gate and live participating/nonparticipating comparison |
| [Neutral gathering](workflows/neutral-gathering.md) | Target/occupancy shield predicate, army-count semantics, and one correlated live collection receipt |
| [Hero Hall recruitment](workflows/hero-hall-recruitment.md) | Free-single animation, Confirm/Close result flow, subsequent paid draw, and reconciliation limits |
| [Resource inventory](workflows/resource-inventory.md) | Recycled Bag rows, partial edge visibility, single versus bulk Use, and full-inventory proof limits |
| [Mail sending](workflows/mail-sending.md) | Player versus alliance send branches, client eligibility checks, and correlated receipt requirements |
| [Provenance and reproduction](PROVENANCE.md) | Build, hashes, artifact locations, and offline reconstruction |

Detailed coverage should grow with scoped work. A complete behavioral reference for every UI, event, server rule, and account state cannot be inferred from a source inventory. Start with the workflow affected by the current task, following its callers and state owners only as far as needed to resolve the question.

## Use during a task

1. Check the workflow note and build provenance. Find the relevant Lua path/symbol through the source map when no note exists.
2. Follow the UI action, request wrapper, response handler, and state updates. For a decision made locally, inspect its actual predicate; a method name or command ID is only a lead.
3. Compare that behavior with the existing automation owner and its observations/tests. Keep product requirements and spending authorization separate from what the game client permits.
4. Record reusable findings with source path, symbol, build, and confidence. Include an automation implication and any material uncertainty.

Use these evidence labels in new notes:

- **Client source verified:** a cited Lua implementation or native instruction sequence was inspected.
- **Offline checked:** a specific reconstruction or extraction check passed; state exactly what was checked.
- **Inferred:** a plausible implication that has not been directly established.
- **Live observed:** only with a dated artifact, target, and recorded action from an authorized live phase.

Current notes contain no live proof of direct API acceptance. Client checks may be supplemented or overridden by the server. Packet transmission, a callback name, a closed window, and a successful process exit are not interchangeable with a verified game outcome.

## Maintaining the reference

Keep one owner for shared facts: provenance here links to PROVENANCE; transport facts belong in REQUEST_PATH; workflow notes own their behavioral findings. Preserve source spellings even when unusual. Cite symbols as well as line numbers, since line numbers can shift. Record a new build before updating claims from newer assets; leave earlier evidence clearly versioned rather than silently mixing builds.

Track concise notes and source pointers. Keep bulk extracted code, APKs, disassembly, and generated indexes ignored. Do not copy credentials, login payloads, account identifiers, or runtime session values into these documents.
