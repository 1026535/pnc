# Archive durability contract

Chat and mail archives use a local-filesystem durability protocol owned by their
archive stores. The protocol is designed for ordinary Python-process termination
and cooperating writers on a validated local filesystem. It does not claim
survival of arbitrary power loss, controller-cache loss, network filesystems,
cloud-sync folders, or removable-media failures.

## Chat transactions

Each chat stream is locked independently of the local day. Its stream identity is
the canonical account/castle/channel path, so a midnight rollover cannot bypass a
pending transaction. The private control data is under
`<chat-root>/.archive-control/`; `pending.json` is a version-one record containing
the resolved archive day, capture timestamp, transcript byte offset and prefix
digest, exact UTF-8 append bytes, next state, and screenshot length/digest.
The stored day is an exact, validated `YYYY-MM-DD` calendar owner; it is not
recomputed by converting the persisted timestamp through the current host
timezone. State validation likewise trusts the physical day owner, preserving
legacy local-day paths without deriving a new day from a timestamp.

For a non-empty change, the store:

1. validates and publishes the screenshot;
2. publishes the complete pending record;
3. appends the recorded bytes and flushes/fsyncs the transcript;
4. publishes the next state through a sibling temporary file and replacement; and
5. retires the pending record only after both payloads are complete.

Recovery validates the whole pending record, screenshot, transcript prefix and
tail, the complete prefix-plus-append bytes, and the next state's length/full
SHA-256 evidence before writing. It appends only the
missing suffix of the recorded bytes. It never regenerates rows, truncates an
unexpected tail, rolls state backward, or treats a short fingerprint as message
equality. An unresolved or malformed record is preserved and reported as a
blocked consistency error.

New `state.json` files use schema version 2 and include `transcript_evidence`:
either `null` (the visible overlap may be inherited from the prior day, but this
day has no committed transcript yet) or `{exists, length, sha256}` for the
complete target-day transcript bytes. Before both an append and a no-delta state
advance, the store verifies the target transcript's regular-file status, complete
line boundaries, exact length, and full digest. A later row after midnight
therefore starts a new transcript at byte offset zero.

Legacy states without this field remain readable conservatively. A non-empty
legacy state is usable only after its same-day transcript exists and validates;
the store calculates evidence while lazily upgrading the state. Missing,
truncated, malformed, or ambiguous legacy data fails closed rather than becoming
an empty baseline. State is a visible overlap window, not a message database.

## Mail completion

Mail payloads are staged and flushed before `metadata.json` is published. New
metadata has schema version 2 and a manifest containing each required payload's
relative name, byte length, and SHA-256 digest. A record is complete only when
the metadata identity matches and every manifest payload verifies. Incomplete
directories remain for inspection and do not suppress a retry. Same-name
captures receive a suffix, so a completed payload is never overwritten.

Legacy metadata without a manifest remains readable only when its identity is
valid and at least one matching `thread.txt` or `thread.png` payload exists.
This is compatibility evidence, not proof of the originally requested archive
mode. Metadata-only and contradictory/corrupt candidates never become completion
markers. A later mode-aware upgrade is intentionally outside this protocol.

## Locks and other writers

Archive locks use stable files and native `msvcrt` or `fcntl` primitives with a
finite acquisition budget. Lock-file existence is not ownership evidence, and
stale locks are never deleted by age or PID heuristics. Every existing managed
path component is checked before mutation: symlinks, Windows junctions/reparse
points, root escapes, non-regular targets, and unexpected layouts are rejected.
The transcript cleanup tool's `--write` path holds the same stream lock across
read, parse, replacement, and state-evidence update; it refuses pending recovery.
There is one production cleanup mutation path, so caller-computed stale text
cannot replace rows added before lock acquisition. Dry-run parsing does not
mutate archives. Chat screenshot extensions and fingerprint-derived names are
validated as safe filename segments before the screenshot directory is created.

Recovery returns the original pending capture timestamp to the store. A current
observation older than recovered work, including work in a skipped or future
day, is rejected before current-call result counts or screenshot flags are
computed. Recovered rows are never reported as rows appended by that call.

The tested codec limits are 16 MiB for a pending JSON record and 12 MiB for its
decoded append payload. Pending reads are bounded to one byte beyond the record
limit before JSON decoding. Atomic replacement uses seven total attempts with
the existing six bounded Windows sharing-denial delays; errors after a replacement
are classified from the resulting bytes on retry.

Stop old archive-writing processes before enabling this writer. Before a
downgrade, stop writers and resolve or inspect every pending record; do not delete
pending control data merely to permit old code to start. A human cleanup edit is
an intentional archive change and may require a subsequent operator review of
the visible-state overlap boundary.

## Operational response

On a blocked recovery, preserve the control directory, transcript, state, and
screenshots. Capture only the stage, opaque operation id, safe relative control
path, byte counts, and error category in diagnostics. Do not copy chat text,
sender names, credentials, or raw pending JSON into logs. Resolve the physical
inconsistency manually, then retry with the same writer; normal recovery does not
delete or rewrite ambiguous history.
