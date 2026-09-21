---
name: durable-state-roundtrip
description: Review persistence-backed safety state for serialization and reconstruction failures. Use when correctness or security depends on state surviving persistence and restart.
---

# Durable State Round-Trip Review

When a safety or security invariant depends on persisted state, verify the invariant across the persistence boundary rather than only in memory.

## Procedure

1. State the invariant that must remain true after reconstruction.
2. Identify the persisted representation and its record/value boundaries.
3. Check whether every accepted logical value can be represented and recovered without ambiguity.
4. Exercise persisted bytes through a fresh reader or newly initialized instance.
5. Verify that successful acceptance implies the same safety state after reconstruction.
6. Consider malformed, partial, interrupted, concurrently modified, replaced, or truncated persistence where those failure modes are relevant.
7. For authorization, replay protection, deduplication, or other safety state, fail closed when durable representation cannot be established.
8. Add regression coverage at the persistence/reconstruction boundary rather than testing only the original in-memory object.

## Evidence discipline

Distinguish remembered state from global fail-closed behavior. A fresh reader refusing all operations because persistence is malformed is safe, but it is not evidence that a particular record was durably remembered.

Separate process-restart evidence from stronger filesystem or power-loss durability claims. Atomic replacement, successful writes, and ordinary restart tests do not by themselves prove crash- or power-loss durability.

Where multiple instances or processes may write the same state, inspect synchronization and path/inode replacement separately from serialization correctness.

## Scope

Apply this reasoning to ledgers, append logs, journals, replay state, authority caches, durable idempotency records, and similar persistence-backed safety mechanisms.

This skill is guidance only. It grants no execution authority and does not override repository policy, review, or testing requirements.
