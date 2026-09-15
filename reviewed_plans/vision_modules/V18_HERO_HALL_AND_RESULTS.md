# V18 — Hero Hall menu and saved recruitment result surfaces

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V01; V02 for automatic Home entry. Deliverable: stable Hero Hall/result identities, content and return ownership without another recruitment.

## Evidence and owner

The [Hero Hall note](../../docs/game-reference/workflows/hero-hall-recruitment.md) and recognition follow-up record a free Single sequence through an unknown summon presentation, Albertus confirmation and fragments/recruit display. A prior transaction was already committed; it must not be repeated for screenshots.

Reuse Hero Hall functions/profile data in `app/pnc/vision`, typed observation and popup ownership, and the existing Hero Hall workflow/operation owners under `app/automation`. No new recruitment executor.

## Implementation

1. Inventory saved stable menu, hero-result and fragment-result frames plus existing tests and receipts. Separate animation from stable actionable surfaces; an animated transition needs bounded settling, not a click-through guess.
2. Qualify independent identity and owned controls for the evidenced stable results. Parse displayed hero/item identity, quantity, result text and current button semantics.
3. Preserve the distinction between a free entry action already dispatched and a paid Recruit button on a result page. Later controls cannot inherit the earlier action's budget.
4. Add explicit close/acknowledgment routes only where existing evidence shows their non-spending behavior and actual destination. Keep result content available to its workflow before returning.
5. Update both publishers and the existing result consumer. A known committed receipt remains terminal even if a presentation frame was unrecognized.

## Acceptance and proof

Extend captured Hero Hall/result tests through real production OCR planning and both publishers. Require the correct result identity/content, owned controls, no paid-action inheritance and no replay after an uncertain/committed result. Use saved transaction evidence; do not manufacture a new result.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks including the existing Hero Hall operation/receipt consumer. One core-runtime live route may inspect Home → Hero Hall → Home. If a saved-result boundary was changed, qualify it offline and state that current live result proof is unavailable unless an already-present result can be safely acknowledged. Save menu frames/trace. Do not recruit, including a nominally free recruitment, merely to validate the screen parser.
