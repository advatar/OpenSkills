# OpenSkills

Reviewed, portable Agent Skills learned from real agent work.

OpenSkills is the public distribution surface for reusable engineering lessons. Raw agent transcripts, private repository content, local paths, credentials, and private review evidence do not belong here.

## Trust model

A published skill is guidance, not authority. Installation never grants permission to execute commands, change files, access secrets, or bypass repository policy.

Skills may be derived from Claude Code, Codex, or other agent runs, but only sanitized, reviewed, generally reusable lessons are published. Canonical private evidence and review receipts remain outside this repository; public provenance records contain only non-sensitive identifiers and evaluation summaries.

## Skills

- [durable-state-roundtrip](skills/durable-state-roundtrip/SKILL.md) — review persistence-backed safety state across serialization and reconstruction boundaries.

The first transfer experiment used a real Claude Code engineering episode and a controlled Codex A/B evaluation. Both the unassisted control and skill-assisted Codex run solved the held-out defect. The demonstrated claim is **cross-harness transfer**, not a proven efficacy, latency, or cost advantage.

See [registry.json](registry.json) for the machine-readable index.
