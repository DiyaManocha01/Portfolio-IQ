# ADR 0007: Append-Only, Hash-Chained Prediction Ledger (Phase 18)

**Status:** Accepted
**Date:** 2026-10-22

## Context

Every prediction the deployed model makes is already stored in the
`predictions` table (Phase 6), but that table is an ordinary mutable row
store: `predict_for_stock()` upserts the same-day row, and nothing stops
an application bug (or a direct DB edit) from silently changing a past
prediction's recorded probability or direction after the fact. For a
project whose stated differentiator includes "a verified public track
record," that's not good enough -- a track record a developer could
quietly edit isn't verifiable by anyone outside this codebase.

## Decision

1. **A new table, `prediction_ledger`**, separate from `predictions`,
   holds an append-only, hash-chained history. Every row's
   `entry_hash = sha256(previous_entry_hash + canonical_json(payload))`.
   Recomputing every hash and comparing to what's stored
   (`verify_chain()`) detects any alteration of any past entry's payload
   -- tested directly: disabling the DB trigger and editing a stored
   field with raw SQL (simulating privileged access that bypasses the
   trigger) still gets caught by `verify_chain()`, because the hash no
   longer matches the payload. That's the actual meaning of
   "tamper-evident" here, demonstrated, not assumed.
2. **Outcomes are recorded as NEW "resolution" entries, never by editing
   the original "prediction" entry.** A prediction's real outcome (did
   the stock actually go up or down the next trading day) only becomes
   knowable after the fact -- naively, that would mean updating the
   original row once the answer is known. Instead, `resolve_due_entries()`
   appends a separate `"resolution"` entry (linked via
   `resolves_entry_id`) onto the end of the SAME hash chain. This is what
   makes the table genuinely insert-only with zero exceptions, rather
   than "insert-only except for this one necessary update."
3. **A Postgres trigger rejects any UPDATE or DELETE against
   `prediction_ledger`** (added in the table's own Alembic migration),
   so append-only is enforced at the database level, not just by
   application code discipline. Verified directly: both an UPDATE and a
   DELETE against a real row raised `psycopg2.errors.RaiseException` from
   the trigger.
4. **Resolution happens lazily**, triggered by `/ledger/track-record` and
   `/ledger/verify` calling `resolve_due_entries()` before computing
   results, rather than a scheduled job -- there's no cron infrastructure
   in this environment, and lazy catch-up is simpler and still correct
   (a resolution is only ever appended once the real next-day close
   price already exists in the cache, never guessed).
5. **New, deliberately UNAUTHENTICATED public endpoints**
   (`GET /ledger/entries`, `GET /ledger/verify`, `GET /ledger/track-record`)
   -- the first no-auth data surface in this app. The entire point of a
   public track record is third-party verifiability without an account
   or trusting this project's own UI; gating it behind a login would
   defeat that purpose.
6. **The ledger starts nearly empty.** No history is backdated or
   fabricated to make the track record look more established than it
   is -- `compute_track_record_stats()`'s response says so directly, not
   just in this ADR. It grows authentically from whatever predictions are
   genuinely made going forward.

## Consequences

- New Alembic migration (`b7c82a9acc47`) adds `prediction_ledger` plus
  the trigger function and two triggers (UPDATE, DELETE). The migration's
  `downgrade()` also explicitly drops the `ledger_entry_type` Postgres
  enum -- `op.drop_table()` alone leaves custom enum types behind, which
  breaks a later re-upgrade (`CREATE TYPE ... already exists`); caught
  and fixed by actually running the downgrade/upgrade cycle twice before
  considering this phase done, not assumed to work.
- `predict_for_stock()` calls `prediction_ledger.append_prediction_entry()`
  only on a genuinely NEW (stock, model, day) prediction, not on repeated
  same-day reads of an already-cached prediction -- verified directly
  (calling `predict_for_stock` twice for the same stock on the same day
  appends exactly one ledger entry, not two).
- This is tamper-EVIDENT, not tamper-PROOF. Someone with full database
  admin access could still truncate the whole table and start a fresh
  chain from scratch, and nothing inside this system would detect that
  from outside the database. A genuinely tamper-proof public record needs
  external anchoring (e.g. periodically publishing the latest hash
  somewhere outside this project's own control) -- explicitly out of
  scope for this phase, stated in `docs/limitations.md`, not glossed
  over.
- No change to the existing `predictions` table or its API --
  `prediction_ledger` is additive, a separate table serving a separate
  (public, verifiable) purpose.

## Alternatives considered

- **Mutating the original prediction row to attach its outcome once
  known.** Rejected: this is exactly the "insert-only except for this one
  necessary update" compromise that would undermine the whole point of
  an append-only ledger. The two-entry-kinds-in-one-chain design avoids
  it entirely.
- **A real blockchain or external anchoring service.** Rejected for this
  phase as genuinely out of scope -- meaningfully more infrastructure
  than a BTech project's track record needs right now; the hash chain +
  DB trigger combination already provides real, demonstrated
  tamper-evidence for the realistic threat model here (an application bug
  or an unprivileged edit), honestly short of protecting against a fully
  privileged attacker.
