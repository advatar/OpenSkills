"""Package integrity and provenance consistency, not scientific qualification."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import validate_skills as validator
from agent_skills import SkillValidationError, parse_frontmatter


class DistributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="openskills-validation-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "skills", self.root / "skills")
        shutil.copyfile(ROOT / "registry.json", self.root / "registry.json")
        self.skill = self.root / "skills" / "durable-state-roundtrip"

    def registry(self) -> dict:
        return json.loads((self.root / "registry.json").read_text(encoding="utf-8"))

    def save_registry(self, registry: dict) -> None:
        (self.root / "registry.json").write_text(json.dumps(registry), encoding="utf-8")

    def provenance(self) -> dict:
        return json.loads((self.skill / "provenance.json").read_text(encoding="utf-8"))

    def save_provenance_and_rehash(self, provenance: dict) -> None:
        (self.skill / "provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
        self.rehash()

    def rehash(self) -> None:
        registry = self.registry()
        registry["skills"][0]["integrity"] = {
            "algorithm": "sha256",
            "files": {path.relative_to(self.skill).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in sorted(self.skill.rglob("*")) if path.is_file()}
        }
        self.save_registry(registry)

    def assert_refused(self) -> None:
        with self.assertRaises(validator.DistributionError):
            validator.validate_repository(self.root)

    def test_committed_distribution_is_consistent(self) -> None:
        self.assertEqual(validator.validate_repository(self.root), ["durable-state-roundtrip"])

    def test_changed_skill_bytes_are_refused(self) -> None:
        with (self.skill / "SKILL.md").open("a", encoding="utf-8") as stream:
            stream.write("\nChanged after review.\n")
        self.assert_refused()

    def test_added_and_missing_payloads_are_refused(self) -> None:
        extra = self.skill / "unexpected.py"
        extra.write_text("print('unreviewed')", encoding="utf-8")
        self.assert_refused()
        extra.unlink()
        (self.skill / "provenance.json").unlink()
        self.assert_refused()

    def test_duplicate_registry_entries_are_refused(self) -> None:
        registry = self.registry()
        registry["skills"].append(dict(registry["skills"][0]))
        self.save_registry(registry)
        self.assert_refused()

    def test_unregistered_skill_directory_is_refused(self) -> None:
        (self.root / "skills" / "unregistered").mkdir()
        self.assert_refused()

    def test_unsafe_registry_paths_are_refused(self) -> None:
        for path in ("../outside", "/tmp/outside", "skills/../outside", "skills\\outside"):
            with self.subTest(path=path):
                registry = self.registry()
                registry["skills"][0]["path"] = path
                self.save_registry(registry)
                self.assert_refused()

    def test_symlinked_package_is_refused(self) -> None:
        external = self.root / "outside"
        self.skill.rename(external)
        self.skill.symlink_to(external, target_is_directory=True)
        self.assert_refused()

    def test_bad_hash_and_unsupported_algorithm_are_refused(self) -> None:
        registry = self.registry()
        registry["skills"][0]["integrity"]["algorithm"] = "sha1"
        self.save_registry(registry)
        self.assert_refused()
        registry["skills"][0]["integrity"]["algorithm"] = "sha256"
        registry["skills"][0]["integrity"]["files"]["SKILL.md"] = "g" * 64
        self.save_registry(registry)
        self.assert_refused()

    def test_provenance_identity_and_status_must_match(self) -> None:
        original = self.provenance()
        for field, value in (("skill", "another-skill"), ("status", "certified")):
            with self.subTest(field=field):
                changed = dict(original)
                changed[field] = value
                self.save_provenance_and_rehash(changed)
                self.assert_refused()

    def test_distinct_control_and_intervention_are_required(self) -> None:
        provenance = self.provenance()
        evaluation = provenance["transfer_evaluation"]
        evaluation["intervention_trace_id"] = evaluation["control_trace_id"]
        self.save_provenance_and_rehash(provenance)
        self.assert_refused()

    def test_provenance_harnesses_must_match_declared_support(self) -> None:
        provenance = self.provenance()
        provenance["transfer_evaluation"]["target_harness"] = "unqualified-harness"
        self.save_provenance_and_rehash(provenance)
        self.assert_refused()

    def test_invalid_metrics_are_refused_even_after_rehash(self) -> None:
        original = self.provenance()
        for field, value in (("control_input_tokens", True), ("control_input_tokens", -1),
                             ("control_input_tokens", 1.5), ("control_duration_seconds", -0.1),
                             ("control_duration_seconds", 10 ** 500),
                             ("control_duration_seconds", float("nan"))):
            with self.subTest(field=field, value=value):
                provenance = json.loads(json.dumps(original))
                provenance["transfer_evaluation"][field] = value
                self.save_provenance_and_rehash(provenance)
                self.assert_refused()

    def test_duplicate_json_keys_are_refused(self) -> None:
        path = self.root / "registry.json"
        content = path.read_text(encoding="utf-8")
        path.write_text(content.replace('"schema":', '"schema": "shadow", "schema":', 1), encoding="utf-8")
        self.assert_refused()

    def test_json_integer_parser_limits_fail_without_traceback(self) -> None:
        (self.root / "registry.json").write_text('{"schema": ' + "9" * 5000 + "}", encoding="utf-8")
        self.assert_refused()

    def test_malformed_skill_cannot_pass_by_updating_digest(self) -> None:
        (self.skill / "SKILL.md").write_text(
            "---\nname: durable-state-roundtrip\ndescription: true\n---\n", encoding="utf-8"
        )
        self.rehash()
        self.assert_refused()


class MetadataTests(unittest.TestCase):
    def test_escaped_surrogates_are_refused_in_fields_and_metadata(self) -> None:
        for field, value in (("description", '"\\uD800"'), ("license", '"\\uD800"'),
                             ("compatibility", '"\\uD800"'), ("allowed-tools", '"\\uD800"'),
                             ("metadata", '{"\\uD800": "value"}'),
                             ("metadata", '{key: "\\uDFFF"}')):
            with self.subTest(field=field), self.assertRaises(SkillValidationError):
                fields = {"name": "example", "description": "Review data."}
                fields[field] = value
                parse_frontmatter("---\n" + "\n".join(f"{key}: {item}" for key, item in fields.items()) + "\n---\n", "example")

    def test_unicode_quoted_and_multiline_yaml_is_supported(self) -> None:
        value = parse_frontmatter('---\nname: "数据分析"\ndescription: >-\n  Review data\n  carefully.\n---\n', "数据分析")
        self.assertEqual(value["description"], "Review data carefully.")

    def test_aliases_duplicate_keys_and_invalid_types_are_refused(self) -> None:
        for suffix in ("description: another description", "metadata: &x {self: *x}",
                       "metadata: {version: 1}", "allowed-tools: [Read]", "authority: granted"):
            with self.subTest(suffix=suffix), self.assertRaises(SkillValidationError):
                parse_frontmatter("---\nname: example\ndescription: Review data.\n" + suffix + "\n---\n", "example")

    def test_name_and_field_bounds_are_enforced(self) -> None:
        for name, description in (("Uppercase", "valid"), ("bad--name", "valid"),
                                  ("a" * 65, "valid"), ("example", "x" * 1025)):
            with self.subTest(name=name), self.assertRaises(SkillValidationError):
                parse_frontmatter(f"---\nname: {name}\ndescription: {description}\n---\n", name)


if __name__ == "__main__":
    unittest.main()
