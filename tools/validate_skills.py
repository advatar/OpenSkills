#!/usr/bin/env python3
"""Validate reviewed distribution bytes without certifying claims or granting authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from agent_skills import SkillValidationError, package_files, skill_directories, validate_skill

ROOT = Path(__file__).resolve().parents[1]
MAX_JSON_BYTES = 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Existing registry uses the product family; provenance names the observed executable.
HARNESS_FAMILIES = {"codex-cli": "codex"}


class DistributionError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DistributionError("JSON contains a duplicate key")
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise DistributionError("JSON numbers must be finite")
    return number


def _invalid_constant(value: str) -> None:
    raise DistributionError("JSON numbers must be finite")


def _json(path: Path) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            raise DistributionError("required JSON must be a regular file")
        with path.open("rb") as stream:
            data = stream.read(MAX_JSON_BYTES + 1)
        if len(data) > MAX_JSON_BYTES:
            raise DistributionError("JSON exceeds the 1 MiB limit")
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant, parse_float=_finite_float)
        if not isinstance(value, dict):
            raise DistributionError("JSON root must be an object")
        return value
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise DistributionError("required JSON is missing, malformed or unreadable") from exc


def _string(mapping: dict[str, Any], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DistributionError(f"{field} must be a non-empty string")
    return value


def _strings(mapping: dict[str, Any], field: str) -> list[str]:
    values = mapping.get(field)
    if not isinstance(values, list) or not values or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise DistributionError(f"{field} must be a non-empty list of strings")
    if len(set(values)) != len(values):
        raise DistributionError(f"{field} contains duplicates")
    return values


def _provenance(entry: dict[str, Any], package: Path) -> None:
    provenance = _json(package / "provenance.json")
    if provenance.get("schema") != "openskills.provenance.v1":
        raise DistributionError("unsupported provenance schema")
    if provenance.get("skill") != entry["name"] or provenance.get("status") != entry["status"]:
        raise DistributionError("provenance identity/status disagrees with the registry")
    source = provenance.get("source")
    evaluation = provenance.get("transfer_evaluation")
    if not isinstance(source, dict) or not isinstance(evaluation, dict):
        raise DistributionError("provenance must contain source and transfer_evaluation objects")
    harnesses = {HARNESS_FAMILIES.get(name, name) for name in entry["harnesses"]}
    observed = (_string(source, "harness"), _string(evaluation, "target_harness"))
    if any(HARNESS_FAMILIES.get(name, name) not in harnesses for name in observed):
        raise DistributionError("provenance harness is not declared in the registry")
    _string(source, "trace_id")
    _string(evaluation, "model")
    control = _string(evaluation, "control_trace_id")
    intervention = _string(evaluation, "intervention_trace_id")
    if control == intervention:
        raise DistributionError("control and intervention must refer to distinct traces")
    for group in ("control", "intervention"):
        _string(evaluation, f"{group}_outcome")
        duration = evaluation.get(f"{group}_duration_seconds")
        if type(duration) not in (int, float) or not (0 <= duration <= sys.float_info.max):
            raise DistributionError("evaluation duration must be a finite non-negative number")
        for metric in ("input_tokens", "output_tokens", "reasoning_output_tokens"):
            value = evaluation.get(f"{group}_{metric}")
            if type(value) is not int or value < 0:
                raise DistributionError("token counts must be non-negative integers")
    _string(evaluation, "conclusion")
    _strings(provenance, "limitations")


def _integrity(entry: dict[str, Any], package: Path) -> None:
    integrity = entry.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
        raise DistributionError("each entry needs sha256 package integrity")
    expected = integrity.get("files")
    if not isinstance(expected, dict) or not expected:
        raise DistributionError("package integrity must name all payload files")
    actual = {path.relative_to(package).as_posix(): path for path in package_files(package)}
    if set(expected) != set(actual):
        raise DistributionError("package files differ from the reviewed integrity manifest")
    if not {"SKILL.md", "provenance.json"}.issubset(actual):
        raise DistributionError("skill and provenance files are required")
    for relative, path in actual.items():
        digest = expected[relative]
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise DistributionError("package digest must be a lowercase SHA-256 hex string")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise DistributionError(f"package digest mismatch: {relative}")


def validate_repository(root: Path = ROOT) -> list[str]:
    """Check static package consistency; do not infer that public claims are proven."""
    try:
        registry = _json(root / "registry.json")
        if registry.get("schema") != "openskills.registry.v1":
            raise DistributionError("unsupported registry schema")
        entries = registry.get("skills")
        if not isinstance(entries, list) or not entries:
            raise DistributionError("registry must contain at least one skill")
        discovered = {path.name: path for path in skill_directories(root / "skills")}
        names = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise DistributionError("registry entries must be objects")
            name = _string(entry, "name")
            if name in names:
                raise DistributionError("duplicate skill identity in registry")
            # Match against discovered directories before following caller-provided paths.
            if name not in discovered or entry.get("path") != f"skills/{name}":
                raise DistributionError("registry path must name its immediate skills directory")
            _string(entry, "status")
            _string(entry, "claim")
            if "agent-skills/1" not in _strings(entry, "formats"):
                raise DistributionError("distribution requires the agent-skills/1 representation")
            _strings(entry, "harnesses")
            package = discovered[name]
            fields = validate_skill(package)
            if fields["name"] != name:
                raise DistributionError("registry identity differs from skill metadata")
            _integrity(entry, package)
            _provenance(entry, package)
            names.append(name)
        if set(names) != set(discovered):
            raise DistributionError("an on-disk skill has no registry entry")
        return names
    except (SkillValidationError, OSError) as exc:
        raise DistributionError(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        names = validate_repository(args.root)
    except DistributionError as exc:
        print(f"OpenSkills validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Validated {len(names)} skill(s): package structure, bytes and provenance consistency only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
