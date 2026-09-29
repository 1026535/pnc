# Chat overlay appearance

On 2026-09-27, the configured `testing` instance showed a full-screen Chat
overlay with two wide tabs, Kingdom and Alliance. The Kingdom tab was active.
The top-left gold Back control and bottom composer matched the older captured
Chat chrome, while the older four-tab Kingdom/Alliance anchors did not match
this layout. This was observed after a VIP daily-reset popup was dismissed in
the M1 Campaign pre-entry batch on candidate `609342c3`.

Provenance: `INC-20260927-m1-v14-resume-preentry-20260927-01-002`, including
the saved 900×1600 frame and recognition-gap sidecar. A sanitized chrome-only
fixture is `tests/data/screen_recognition/chat_kingdom_two_tab_20260927.png`;
its tracked profile recognizes the current Kingdom-active layout and measures
the owned Back, tabs, and input field. Confidence is high for this one observed
screen. The installed client build and the Alliance-active two-tab appearance
were not established.

In a later nonspending run on the same date and candidate `12cd84f6`, the
measured Chat Back restored `PNC_MORE_MENU`, the surface that had opened Chat.
The shared navigation graph now accepts More as a Chat Back destination and
replans through Settings to Home. The saved post-Back frame is in Devin run
`m1-v14-two-tab-chat-corrected-20260927-02`, turn 002. This route was observed
once; other invoking surfaces may restore to Home or World Map.

Automation must qualify Chat from a fresh frame before using its owned Back
control. An unrecognized full-screen overlay blocks castle identity preflight
and Campaign navigation; do not guess Back or treat the blocked Campaign cases
as feature failures.
