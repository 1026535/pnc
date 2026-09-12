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
the original local day, capture timestamp, transcript byte offset and prefix
digest, exact UTF-8 append bytes, next state, and screenshot length/digest.

For a non-empty change, the store:

1. validates and publishes the screenshot;
2. publishes the complete pending record;
3. appends the recorded bytes and flushes/fsyncs the transcript;
4. publishes the next state through a sibling temporary file and replacement; and
5. retires the pending record only after both payloads are complete.

Recovery validates the whole pending record, screenshot, transcript prefix and
tail, and old/new state classification before writing. It appends only the
missing suffix of the recorded bytes. It never regenerates rows, truncates an
unexpected tail, rolls state backward, or treats a short fingerprint as message
equality. An unresolved or malformed record is preserved and reported as a
blocked consistency error.

Existing `state.json` files remain readable. They are validated more strictly on
load, but are not bulk-migrated. An old transcript is preserved byte-for-byte;
an incomplete or malformed boundary requires operator review rather than guessed
repair. State is a visible overlap window, not a message database.

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
stale locks are never deleted by age or PID heuristics. The transcript cleanup
tool's `--write` path uses the same stream lock, refuses pending recovery, and
publishes its replacement atomically. Dry-run parsing does not mutate archives.

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
