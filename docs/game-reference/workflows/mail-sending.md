# Mail sending boundaries

**Build:** [PNC 5.0.203 / version code 233](../PROVENANCE.md).
**Evidence:** client source inspected September 13; no mail was sent for this
note. Later live captures may use downloaded updates and cannot be assumed to
match this package.

## Verified client behavior

`uis/mail/mailwritewin.lua`, `MailWriteWin:OnSendHandler` (line 204), checks a
Campaign progress rule before sending. The ordinary player path also checks the
configured castle-level rule. These are dynamic game rules: this inspection does
not establish a universal chapter or minimum level. The handler rejects the
current player's own name, missing player target and empty content.

The ordinary player branch constructs target name, title and content and calls
`PrivateChatSend.RequireAddChat`, or its special-content branch after
`PrivateChatData.BeforeSendProc`. Alliance and season-alliance branches instead
call `MailxSend.RequireUnionAllMemberMails` and
`RequireSeasonUnionAllMemberMails`. The latter wrappers are in
`commands/mailx/mailxcommand.lua` (lines 377 and 638). A single generic Mailx
command therefore does not describe all UI Send behavior.

`MailWriteWin:UpdateWins` (line 91) handles the relevant send update commands by
showing the localized success message, setting the sending flag and closing the
compose window. The ordinary close handler is also available independently.
Window disappearance alone is insufficient evidence of a successful send.

## Automation implications and limits

Use the existing canonical typed mail parameters and public UI workflow. Source
names are evidence for boundaries, never instructions to call the game service.
The sender's own active character is a poor test recipient because the inspected
client rejects it; another user-owned character is a suitable candidate only
after its exact name/kingdom and message are specified by the user.

The current [capture findings](../../../reviewed_plans/PNC_NON_YOLO_CAPTURE_FINDINGS_20260913.md)
contain player mailbox, empty Compose and field-entry evidence, with no Send.
A future receipt must be correlated to the approved recipient and new payload;
a prior message containing the same subject or first line is not evidence that
the new action succeeded. If production observation cannot prove the result,
report it as unconfirmed and do not automatically resend.

**Confidence:** high for the inspected client branches and checks; live
eligibility, server acceptance, recipient disambiguation and current success
publication remain unproven. The native Login route is separate and is not
covered by this note. Raw mail/account evidence belongs in ignored artifacts;
do not copy private messages or login values into tracked fixtures.
