"""Tests for the draft persona_redteam pool exporter and the intake/dedup extensions.

    python3 -m unittest discover -s phase1_safe/tests -t .
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from phase1_safe import export_pool, run
from phase1_safe.adapters import cactus
from phase1_safe.export_pool import (UnresolvedFieldError, compare_with_manifest, export_rows,
                                     validate_mapping, validate_pool_rows)
from phase1_safe.select_records import normalized_thought, select_records

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_counseling_rows.json"
DRAFT_MAPPING = Path(__file__).resolve().parents[1] / "mappings" / "redteam_pool_draft.json"


def load_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def resolved_mapping():
    """Test-only mapping that fills every TODO with one candidate. Not a decision."""
    m = json.loads(DRAFT_MAPPING.read_text(encoding="utf-8"))
    m["mapping_id"] = "test-resolved"
    m["fields"]["condition"] = {"strategy": "copy", "path": "record.intake_form.presenting_problem"}
    m["fields"]["background"] = {"strategy": "join", "paths": ["record.intake_form.family_details",
                                                               "record.intake_form.past_history"]}
    m["fields"]["style_reference"] = {"strategy": "first_text", "path": "persona.style_references"}
    m["fields"]["distress_tags"] = {"strategy": "copy", "path": "record.patterns"}
    m["fields"]["resistance"] = {"strategy": "copy", "path": "persona.resistance.status"}
    return m


class BuildMixin:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.assertEqual(run.main(["build", "--input", str(FIXTURE), "--out-dir", str(self.dir / "b")]), 0)
        self.records = load_jsonl(self.dir / "b" / "records.jsonl")
        self.personas = load_jsonl(self.dir / "b" / "personas.jsonl")

    def tearDown(self):
        self.tmp.cleanup()


class IntakeSections(unittest.TestCase):
    def test_sections_verbatim(self):
        form = ("Name: A\nAge: 30\nEducation: College\nMarital Status: Single\nFamily Details: Lives with a cat\n\n"
                "2. Presenting Problem\nWorried about\nwork.\n\n3. Reason for Seeking Counseling\nWants help.\n\n"
                "4. Past History (including medical history)\nNone before.\n\n"
                "5. Academic/occupational functioning level: Fine at work.\nDaily life: Okay.\n\n"
                "6. Social Support System\nA few friends.")
        out = cactus.parse_intake_sections(form)
        self.assertEqual(out, {"education": "College", "marital_status": "Single",
                               "family_details": "Lives with a cat", "presenting_problem": "Worried about work.",
                               "past_history": "None before.", "functioning": "Fine at work. Daily life: Okay.",
                               "social_support": "A few friends."})

    def test_alternate_social_support_title_and_placeholders(self):
        form = ("Education: Not specified\n6. Is there anyone you can talk to or get help from when you "
                "encounter difficulties or problems?\nMy sister.")
        out = cactus.parse_intake_sections(form)
        self.assertIsNone(out["education"])
        self.assertEqual(out["social_support"], "My sister.")
        self.assertIsNone(out["presenting_problem"])

    def test_record_keeps_basic_and_extra_fields(self):
        rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
        rec = cactus.to_record(rows[0], 0)
        self.assertEqual(rec["intake_form"]["age"], "34")
        self.assertEqual(rec["intake_form"]["presenting_problem"], "Feels stressed about everyday matters.")


class ThoughtDedup(unittest.TestCase):
    def test_normalized_thought_keeps_earliest_row(self):
        rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
        recs = [cactus.to_record(r, i) for i, r in enumerate(rows)]
        variant = copy.deepcopy(recs[10])
        variant.update(source_id="cactus-000099", thought="  " + recs[10]["thought"].upper() + " ")
        variant["dialogue"] = [{"turn_id": 0, "speaker": "client", "text": "A different opening line here."}]
        kept, stats = select_records(recs + [variant], dedup="thought")
        ids = [r["source_id"] for r in kept]
        self.assertIn("cactus-000010", ids)
        self.assertNotIn("cactus-000099", ids)
        self.assertEqual(stats["dropped_duplicate_thought"], 2)  # row 14 (same thought as 9) + variant
        self.assertEqual(normalized_thought(variant), normalized_thought(recs[10]))

    def test_invalid_mode(self):
        with self.assertRaises(ValueError):
            select_records([], dedup="name")


class MappingValidation(unittest.TestCase):
    def test_draft_mapping_is_valid_and_has_todos(self):
        m = json.loads(DRAFT_MAPPING.read_text(encoding="utf-8"))
        self.assertEqual(validate_mapping(m), [])
        unresolved = {f for f, s in m["fields"].items() if s["strategy"] == "unresolved"}
        self.assertTrue({"condition", "background", "style_reference"} <= unresolved)

    def test_bad_mappings(self):
        m = json.loads(DRAFT_MAPPING.read_text(encoding="utf-8"))
        bad = copy.deepcopy(m)
        del bad["fields"]["thought"]
        bad["fields"]["condition"] = {"strategy": "guess"}
        bad["fields"]["persona_id"] = {"strategy": "unresolved"}
        bad["fields"]["extra"] = {"strategy": "copy", "path": "x"}
        errs = " | ".join(validate_mapping(bad))
        for needle in ("fields.thought: missing", "fields.condition: strategy", "persona_id: cannot be unresolved",
                       "fields.extra: not a pool field"):
            self.assertIn(needle, errs)


class Export(BuildMixin, unittest.TestCase):
    def test_draft_mapping_fails_by_default(self):
        m = json.loads(DRAFT_MAPPING.read_text(encoding="utf-8"))
        with self.assertRaises(UnresolvedFieldError):
            export_rows(self.records, self.personas, m)

    def test_dry_run_omits_unresolved_and_records_provenance(self):
        m = json.loads(DRAFT_MAPPING.read_text(encoding="utf-8"))
        rows, prov = export_rows(self.records, self.personas, m, on_unresolved="omit")
        self.assertEqual(len(rows), len(self.personas))
        self.assertEqual(validate_pool_rows(rows), [])
        for row, p in zip(rows, prov):
            self.assertTrue({"condition", "background", "style_reference", "distress_tags", "resistance"}.isdisjoint(row))
            self.assertEqual(p["omitted_fields"]["condition"], "unresolved")
            self.assertEqual(p["persona_id"], row["persona_id"])
            self.assertTrue(p["source_id"].startswith("cactus-"))
            self.assertNotIn("source_id", row)  # provenance lives in the sidecar

    def test_values_are_verbatim_source(self):
        rows, _ = export_rows(self.records, self.personas, resolved_mapping())
        by_id = {p["persona_id"]: p for p in self.personas}
        recs = {r["source_id"]: r for r in self.records}
        for row in rows:
            persona = by_id[row["persona_id"]]
            rec = recs[persona["source_id"]]
            self.assertEqual(row["thought"], rec["thought"])
            self.assertEqual(row["patterns"], rec["patterns"])
            self.assertEqual(row["style_reference"], persona["style_references"][0]["text"])
            if "condition" in row:
                self.assertEqual(row["condition"], rec["intake_form"]["presenting_problem"])
        self.assertEqual(validate_pool_rows(rows), [])

    def test_never_writes_null(self):
        rows, prov = export_rows(self.records, self.personas, resolved_mapping())
        for row in rows:
            self.assertNotIn(None, row.values())
        # cactus-000001 has no presenting problem / family details / past history in the fixture
        p = next(p for p in prov if p["source_id"] == "cactus-000001")
        self.assertEqual(p["omitted_fields"].get("condition"), "source_missing")
        self.assertEqual(p["omitted_fields"].get("background"), "source_missing")
        # cactus-000002 has gender and occupation placeholders -> descriptor without them, no "person"
        row = next(r for r, q in zip(rows, prov) if q["source_id"] == "cactus-000002")
        self.assertEqual(row["descriptor"], "a 29-year-old")

    def test_legacy_formats(self):
        rows, _ = export_rows(self.records, self.personas, resolved_mapping())
        row = next(r for r in rows if r["persona_id"] == "p1-cactus-000000")
        self.assertEqual(row["descriptor"], "a 34-year-old female Library Assistant")
        self.assertTrue(row["cognitive_distortion"].startswith("catastrophizing: If my presentation"))

    def test_missing_record_is_an_error(self):
        with self.assertRaises(ValueError):
            export_rows(self.records[1:], self.personas, resolved_mapping())


class PoolValidation(unittest.TestCase):
    def test_contract_violations(self):
        rows = [{"persona_id": "a", "condition": None}, {"persona_id": "a"}, {"persona_id": " "},
                {"persona_id": "b", "patterns": "x"}, {"persona_id": "c", "descriptor": ["x"]}]
        errs = " | ".join(validate_pool_rows(rows, expected_rows=2000))
        for needle in ("expected 2000 rows", "condition must be a string", "duplicate persona_id",
                       "non-empty string", "patterns must be a list", "descriptor must be a string"):
            self.assertIn(needle, errs)

    def test_valid_rows(self):
        self.assertEqual(validate_pool_rows([{"persona_id": "a", "thought": "t", "patterns": ["p"]}], 1), [])


class CliAndManifest(BuildMixin, unittest.TestCase):
    def cli(self, out, *extra, mapping=DRAFT_MAPPING):
        return export_pool.main(["--records", str(self.dir / "b" / "records.jsonl"),
                                 "--personas", str(self.dir / "b" / "personas.jsonl"),
                                 "--mapping", str(mapping), "--out", str(out), *extra])

    def test_cli_fails_on_unresolved_and_writes_nothing(self):
        out = self.dir / "pool.jsonl"
        self.assertEqual(self.cli(out), 2)
        self.assertFalse(out.exists())

    def test_cli_dry_run_reproducible_with_sidecars(self):
        a, b = self.dir / "a" / "pool.jsonl", self.dir / "b2" / "pool.jsonl"
        self.assertEqual(self.cli(a, "--on-unresolved", "omit"), 0)
        self.assertEqual(self.cli(b, "--on-unresolved", "omit"), 0)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        report = json.loads((a.parent / "pool.export_manifest.json").read_text())
        self.assertEqual(report["rows"], 8)
        self.assertEqual(report["fields_present"]["condition"], 0)
        self.assertEqual(len(load_jsonl(a.parent / "pool.provenance.jsonl")), 8)

    def test_cli_expected_rows_mismatch(self):
        self.assertEqual(self.cli(self.dir / "p.jsonl", "--on-unresolved", "omit", "--expected-rows", "2000"), 3)

    def test_compare_with_manifest(self):
        out = self.dir / "pool.jsonl"
        self.assertEqual(self.cli(out, "--on-unresolved", "omit"), 0)
        data = out.read_bytes()
        import hashlib
        manifest = self.dir / "DATA_MANIFEST.json"
        manifest.write_text(json.dumps({"files": [{"path": "personas/cactus_distress_n2000.jsonl", "rows": 8,
                                                   "bytes": len(data), "sha256": "0" * 64}]}))
        cmp = compare_with_manifest(out, manifest)
        self.assertTrue(cmp["rows"]["match"] and cmp["bytes"]["match"])
        self.assertFalse(cmp["sha256"]["match"])
        self.assertEqual(cmp["sha256"]["actual"], hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()
