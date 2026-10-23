"""Bounded Agent Skills validation for distribution tooling, never authorization.

Format baseline: agentskills/agentskills@69ef37e9424c0a7ea9dd2293b559e43ec8176379.
The packaging profile additionally refuses ambiguous YAML, symbolic links and special
files. These local ingestion limits are not claimed as universal format requirements.
PyYAML is a tooling dependency; the OMPS reference runtime does not import this module.
"""

from __future__ import annotations

import os
import stat
import unicodedata
from pathlib import Path
from typing import Any

import yaml

MAX_SKILL_BYTES = 1024 * 1024
MAX_FRONTMATTER_BYTES = 16 * 1024
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_ENTRIES = 1024
MAX_YAML_NODES = 256
MAX_YAML_DEPTH = 16
FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


class SkillValidationError(ValueError):
    """The package is invalid or exceeds this distribution profile's limits."""


class _UniqueSafeLoader(yaml.SafeLoader):
    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self.node_count = 0
        self.node_depth = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            raise SkillValidationError("YAML aliases are not supported by the packaging profile")
        self.node_count += 1
        self.node_depth += 1
        try:
            if self.node_count > MAX_YAML_NODES or self.node_depth > MAX_YAML_DEPTH:
                raise SkillValidationError("YAML metadata exceeds complexity limits")
            return super().compose_node(parent, index)
        finally:
            self.node_depth -= 1

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[str, Any]:
        if not isinstance(node, yaml.MappingNode):
            raise SkillValidationError("YAML metadata must be a mapping")
        result: dict[str, Any] = {}
        for key_node, value_node in node.value:
            if not isinstance(key_node, yaml.ScalarNode) or key_node.tag != "tag:yaml.org,2002:str":
                raise SkillValidationError("YAML mapping keys must be strings; merge keys are unsupported")
            key = self.construct_object(key_node, deep=True)
            if key in result:
                raise SkillValidationError("YAML metadata contains a duplicate mapping key")
            result[key] = self.construct_object(value_node, deep=True)
        return result


def _unicode_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _string(fields: dict[str, Any], key: str, limit: int | None = None) -> str:
    value = fields.get(key)
    if not _unicode_string(value) or not value.strip():
        raise SkillValidationError(f"{key} must be a non-empty Unicode scalar string")
    if limit is not None and len(value) > limit:
        raise SkillValidationError(f"{key} exceeds {limit} characters")
    return value


def parse_frontmatter(content: str, directory_name: str) -> dict[str, Any]:
    """Parse data only; unknown fields or declarations never confer permissions."""
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n \t") != "---":
        raise SkillValidationError("SKILL.md must begin with a YAML frontmatter delimiter")
    closing = next((i for i, line in enumerate(lines[1:], start=1)
                    if line.rstrip("\r\n \t") == "---"), None)
    if closing is None:
        raise SkillValidationError("SKILL.md has no closing YAML frontmatter delimiter")
    frontmatter = "".join(lines[1:closing])
    if len(frontmatter.encode("utf-8")) > MAX_FRONTMATTER_BYTES:
        raise SkillValidationError("YAML frontmatter exceeds the 16 KiB packaging limit")
    try:
        fields = yaml.load(frontmatter, Loader=_UniqueSafeLoader)
    except yaml.YAMLError as exc:
        # Do not echo untrusted metadata or embedded credentials in diagnostics.
        raise SkillValidationError("SKILL.md contains malformed or unsupported YAML") from exc
    if not isinstance(fields, dict):
        raise SkillValidationError("YAML frontmatter must be a mapping")
    if set(fields) - FIELDS:
        raise SkillValidationError("unsupported frontmatter fields; put extensions in metadata")
    name = _string(fields, "name", 64)
    normalized = unicodedata.normalize("NFKC", name)
    if (name != name.strip() or len(normalized) > 64 or normalized != normalized.lower()
            or normalized.startswith("-") or normalized.endswith("-") or "--" in normalized
            or not all(character.isalnum() or character == "-" for character in normalized)):
        raise SkillValidationError("name must use lowercase alphanumeric characters and single hyphens")
    if normalized != unicodedata.normalize("NFKC", directory_name):
        raise SkillValidationError("frontmatter name must match its directory")
    _string(fields, "description", 1024)
    for field, limit in (("compatibility", 500), ("license", None), ("allowed-tools", None)):
        if field in fields:
            _string(fields, field, limit)
    if "metadata" in fields:
        metadata = fields["metadata"]
        if not isinstance(metadata, dict) or any(
            not _unicode_string(key) or not _unicode_string(value) for key, value in metadata.items()
        ):
            raise SkillValidationError("metadata must map Unicode scalar string keys to string values")
    return fields


def package_files(directory: Path) -> list[Path]:
    """Enumerate a stable local package without following links or opening devices."""
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise SkillValidationError("skill must be a regular directory, not a symbolic link")
        pending = [directory]
        result: list[Path] = []
        count = total = 0
        while pending:
            current = pending.pop()
            with os.scandir(current) as entries:
                for entry in entries:
                    count += 1
                    if count > MAX_PACKAGE_ENTRIES:
                        raise SkillValidationError("skill exceeds the 1024-entry packaging limit")
                    info = entry.stat(follow_symlinks=False)
                    path = Path(entry.path)
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(path)
                    elif stat.S_ISREG(info.st_mode):
                        total += info.st_size
                        if total > MAX_PACKAGE_BYTES:
                            raise SkillValidationError("skill exceeds the 16 MiB packaging limit")
                        result.append(path)
                    else:
                        raise SkillValidationError("skill contains a symbolic link or special file")
        return sorted(result)
    except OSError as exc:
        raise SkillValidationError("skill package cannot be inspected") from exc


def validate_skill(directory: Path) -> dict[str, Any]:
    files = package_files(directory)
    entrypoint = directory / "SKILL.md"
    if entrypoint not in files:
        raise SkillValidationError("missing required SKILL.md")
    try:
        with entrypoint.open("rb") as stream:
            data = stream.read(MAX_SKILL_BYTES + 1)
        if len(data) > MAX_SKILL_BYTES:
            raise SkillValidationError("SKILL.md exceeds the 1 MiB packaging limit")
        content = data.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise SkillValidationError("SKILL.md must be readable UTF-8") from exc
    return parse_frontmatter(content, directory.name)


def skill_directories(root: Path) -> list[Path]:
    """Discover immediate skill directories; ignore ordinary root documentation."""
    try:
        if root.is_symlink() or not root.is_dir():
            raise SkillValidationError("skills must be a regular directory, not a symbolic link")
        result = []
        with os.scandir(root) as entries:
            for count, entry in enumerate(entries, start=1):
                if count > MAX_PACKAGE_ENTRIES:
                    raise SkillValidationError("skills directory exceeds the entry limit")
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    result.append(Path(entry.path))
                elif not stat.S_ISREG(mode):
                    raise SkillValidationError("skills directory contains a symbolic link or special file")
        return sorted(result)
    except OSError as exc:
        raise SkillValidationError("skills directory cannot be inspected") from exc
