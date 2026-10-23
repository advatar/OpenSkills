# Agent Skills distribution checks

OpenSkills remains the reviewed public distribution surface. This validation adds no
registry service, installer, model call, execution grant or new policy authority.

The format baseline is the [Agent Skills specification](https://agentskills.io/specification)
at upstream commit
[`69ef37e9424c0a7ea9dd2293b559e43ec8176379`](https://github.com/agentskills/agentskills/tree/69ef37e9424c0a7ea9dd2293b559e43ec8176379),
specification blob `d9a2db099d905da8b879a5c6f996728073985279`. This is a source pin,
not a claimed upstream release. The upstream demonstration library is not a runtime
dependency. `tools/agent_skills.py` is shared in behavior with OpenMind's distribution
validator, while each repository retains independent tests and deployment.

## What the check establishes

- A registry entry resolves to its immediate `skills/<name>` directory, with unique
  identity and no unregistered skill directory.
- `SKILL.md` contains valid YAML and conforming required/optional metadata; Unicode
  names, quoted strings and multiline descriptions work.
- Every package file is covered by a lowercase SHA-256 digest in the registry's
  additive `integrity` field. Missing, extra or modified files fail validation.
- Provenance identifies the same skill/status, names declared harnesses, distinguishes
  control and intervention traces, and supplies well-typed non-negative metrics and
  explicit limitations. Existing `codex-cli` provenance maps to the registry's `codex`
  product family for this comparison; stored evidence is not rewritten.

These hashes identify bytes. They are not signatures, proof of a trusted publisher,
proof of clinical safety, proof that private trace references resolve, or evidence that
a skill improved efficacy, latency or cost. Editing both a package and its registry
digests still requires normal review. The original transfer candidate's evidence and
qualification claims remain unchanged.

## Local ingestion profile

Validation never executes package code or treats `allowed-tools` as permission.
Duplicate JSON/YAML keys, non-finite JSON numbers, YAML aliases and merge keys,
unsafe YAML tags, invalid UTF-8, escaped lone surrogates, symbolic links and special files are refused.
Limits are 1 MiB per `SKILL.md` or JSON record, 16 KiB of frontmatter, 256 YAML
nodes, 16 YAML levels, 1,024 package entries and 16 MiB per skill. These are local
packaging restrictions, not additions to the upstream standard. Validate stable
directory snapshots; this CLI is not a race-safe sandbox for hostile concurrent writes.

## Run and update

```sh
python3 -m venv .venv-validation
.venv-validation/bin/python -m pip install -r requirements-validation.txt
.venv-validation/bin/python -m unittest discover -s tests -v
.venv-validation/bin/python tools/validate_skills.py
```

After a reviewed package change, compute each file's SHA-256 and update its registry
digest explicitly. The validator never repairs hashes automatically or alters evidence
to pass a check. Preserve provenance limitations; a new efficacy claim requires new
evaluation and review, not a changed manifest.

The upstream format's license does not license skill content. This change assigns no
license to existing OpenSkills material; publishing terms remain an owner decision.
