# Plans

This is the canonical home for Puzzles & Conquest planning documents.

## Categories

- [`dropped/`](dropped/): retired or superseded plans kept for historical context. These documents are not current execution authority.
- [`completed/`](completed/): implementation, validation, and integration records for completed slices. A completed record does not imply that the broader feature is complete.
- [`themed/`](themed/): current plans grouped by module or theme.
- [`reviewed/`](reviewed/): plans with an explicit review record, plus review, audit, findings, handoff, and validation records, grouped by module or theme.

## Themes

- [`account-runtime/`](themed/account-runtime/): account, castle, BlueStacks, and runtime targeting.
- [`chat/`](themed/chat/): chat navigation and Kingdom Chat monitoring.
- [`core/`](themed/core/): replacement core, workflow contracts, architecture, and preflight.
- [`gameplay/`](themed/gameplay/): buildings, gathering, campaign, and other gameplay routes.
- [`mail/`](themed/mail/): mail and scheduled-mail workflows.
- [`operations/`](themed/operations/): coordination and operational follow-ups.
- [`pet-workshop/`](themed/pet-workshop/): Pet Workshop roadmap, plans, and implementation packets.
- [`testing/`](themed/testing/): test architecture, parity, and selection plans.
- [`vision/`](themed/vision/): recognition, OCR, selectors, popup recovery, and the numbered vision modules.
- [`world-map/`](themed/world-map/): world-map navigation, movement, search, and traversal.

Each theme may also have a matching directory under [`reviewed/`](reviewed/) for its review records.

## Placement rule

Use the category directory first, then the narrowest stable module/theme directory. Keep historical material in `dropped/`; move an implementation record to `completed/` only when the document itself records a completed or accepted slice. Plans with remaining work stay under `themed/`; a plan with an explicit review record is colocated with that record under `reviewed/`; review records and evidence stay under `reviewed/`.
