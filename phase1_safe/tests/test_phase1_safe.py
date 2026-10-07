"""Offline tests for phase1_safe (handoff §11.1). Run from repo root:

    python3 -m unittest discover -s phase1_safe/tests -t .
"""
from __future__ import annotations

import copy
import json
import random
import tempfile
import unittest
from pathlib import Path

from phase1_safe import run
from phase1_safe.adapters import cactus
from phase1_safe.bind import apply_bindings, validate_binding
from phase1_safe.compile_spec import compile_spec
from phase1_safe.extract import build_persona, extract_resistance
from phase1_safe.profile import profile_records
from phase1_safe.schema import PLACEHOLDER_TARGET_ID, validate_persona, validate_record
from phase1_safe.select_records import describe_rule, sample_records, select_records

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_counseling_rows.json"
RULE = describe_rule(("negative",), True, True)


def load_fixture_records():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [cactus.to_record(r, i) for i, r in enumerate(rows)]


class IntakeParsing(unittest.TestCase):
    def test_inline_and_sections(self):
        form = ("1. Basic Information\nName: A B\nAge: 34\nGender: female\nOccupation: Clerk\n\n"
                "3. Reason for Seeking Counseling\nWorry about\nexams.\n\n4. Past History\nNone.")
        out = cactus.parse_intake_form(form)
        self.assertEqual(out["age"], "34")
        self.assertEqual(out["occupation"], "Clerk")
        self.assertEqual(out["reason_for_seeking_help"], "Worry about exams.")

    def test_next_line_values(self):
        out = cactus.parse_intake_form("Name:\nSam\nAge:\n42\nGender:\nmale\n")
        self.assertEqual((out["name"], out["age"], out["gender"]), ("Sam", "42", "male"))

    def test_empty_occupation_does_not_swallow_next_field(self):
        # Regression for build_personas.py producing "a 42-year-old male Education:".
        out = cactus.parse_intake_form("Age: 42\nOccupation:\nEducation: Bachelor's degree\n")
        self.assertIsNone(out["occupation"])

    def test_placeholders_become_null_not_defaults(self):
        out = cactus.parse_intake_form("Age: 30\nGender: Not specified\nOccupation: Undisclosed\n")
        self.assertIsNone(out["gender"])
        self.assertIsNone(out["occupation"])
        self.assertIsNone(out["reason_for_seeking_help"])

    def test_non_string_input(self):
        self.assertTrue(all(v is None for v in cactus.parse_intake_form(None).values()))


class DialogueParsing(unittest.TestCase):
    def test_string_with_continuation(self):
        turns = cactus.parse_dialogue("Counselor: Hi.\nClient: First line\nsecond line\nTherapist: Ok.")
        self.assertEqual([t["speaker"] for t in turns], ["counselor", "client", "counselor"])
        self.assertEqual(turns[1]["text"], "First line second line")
        self.assertEqual([t["turn_id"] for t in turns], [0, 1, 2])

    def test_list_input_and_empty_turns_renumbered(self):
        turns = cactus.parse_dialogue([{"role": "counselor", "content": "Hi"},
                                       {"speaker": "client", "text": "  "},
                                       {"speaker": "client", "text": "Hello"}])
        self.assertEqual([(t["turn_id"], t["speaker"]) for t in turns], [(0, "counselor"), (1, "client")])

    def test_patterns_string_or_list(self):
        self.assertEqual(cactus.parse_patterns("a, b, a"), ["a", "b"])
        self.assertEqual(cactus.parse_patterns(["x", " y "]), ["x", "y"])
        self.assertEqual(cactus.parse_patterns(None), [])


class RecordsAndSelection(unittest.TestCase):
    def setUp(self):
        self.records = load_fixture_records()

    def test_records_valid_and_ids_preserved(self):
        for r in self.records:
            self.assertEqual(validate_record(r), [], r["source_id"])
        self.assertEqual(self.records[0]["source_id"], "cactus-000000")
        rec = cactus.to_record({"id": 77, "dialogue": "Client: hi there"}, 0)
        self.assertEqual(rec["source_id"], "cactus-77")

    def test_filter_stats(self):
        kept, stats = select_records(self.records)
        self.assertEqual(stats, {"total": 15, "dropped_attitude": 2, "dropped_missing_thought": 1,
                                 "dropped_missing_patterns": 1, "dropped_duplicate_dialogue": 1,
                                 "dropped_no_client_turn": 1, "dropped_duplicate_client": 1, "kept": 8})
        self.assertTrue(all(r["attitude"] == "negative" for r in kept))
        self.assertEqual(sum(stats[k] for k in stats if k.startswith("dropped")) + stats["kept"], stats["total"])

    def test_one_dialogue_per_client_unless_disabled(self):
        kept, _ = select_records(self.records)
        ids = {r["source_id"] for r in kept}
        self.assertIn("cactus-000009", ids)          # smallest source_id of that client wins
        self.assertNotIn("cactus-000014", ids)
        kept_all, stats = select_records(self.records, dedup="none")
        self.assertEqual(len(kept_all), 9)
        self.assertNotIn("dropped_duplicate_client", stats)

    def test_min_age_filter(self):
        kept, stats = select_records(self.records, min_age=30)
        self.assertTrue(all(int(r["intake_form"]["age"]) >= 30 for r in kept))
        self.assertEqual(stats["dropped_age"], 4)  # ages 29, 27, 19 + row 14 (age 27, checked before client dedup)
        self.assertEqual(stats["kept"], 5)

    def test_same_seed_same_selection_regardless_of_input_order(self):
        kept, _ = select_records(self.records)
        shuffled = kept[:]
        random.Random(123).shuffle(shuffled)
        a = [r["source_id"] for r in sample_records(kept, 4, seed=7)]
        b = [r["source_id"] for r in sample_records(shuffled, 4, seed=7)]
        self.assertEqual(a, b)

    def test_different_seeds_can_differ(self):
        kept, _ = select_records(self.records)
        picks = {tuple(r["source_id"] for r in sample_records(kept, 3, seed=s)) for s in range(10)}
        self.assertGreater(len(picks), 1)

    def test_n_larger_than_pool_returns_all(self):
        kept, _ = select_records(self.records)
        self.assertEqual(len(sample_records(kept, 999, seed=0)), len(kept))


class PersonaExtraction(unittest.TestCase):
    def setUp(self):
        self.kept, _ = select_records(load_fixture_records())

    def build(self, rec, **kw):
        return build_persona(rec, seed=0, selection_rule=RULE, **kw)

    def test_valid_and_traceable(self):
        for rec in self.kept:
            p = self.build(rec, resistance_method="lexical-v1")
            self.assertEqual(validate_persona(p), [], p["persona_id"])
            client_turns = {t["turn_id"]: t["text"] for t in rec["dialogue"] if t["speaker"] == "client"}
            for ref in p["style_references"]:
                self.assertEqual(client_turns[ref["turn_id"]], ref["text"])  # verbatim source text
            self.assertEqual(p["psychological_state"]["thought"], rec["thought"])
            self.assertEqual(p["psychological_state"]["patterns"], rec["patterns"])

    def test_no_fabricated_fields(self):
        by_id = {r["source_id"]: r for r in self.kept}
        p = self.build(by_id["cactus-000002"])
        self.assertIsNone(p["persona"]["gender"])
        self.assertIsNone(p["persona"]["occupation"])
        self.assertEqual(p["psychological_state"]["affect"], {"value": None, "status": "unknown"})

    def test_style_k_and_length_bounds(self):
        rec = self.kept[0]
        self.assertEqual(len(self.build(rec, style_k=1)["style_references"]), 1)
        self.assertEqual(self.build(rec, style_min_chars=10_000)["style_references"], [])

    def test_resistance_default_unknown_even_if_negative(self):
        p = self.build(self.kept[0])
        self.assertEqual(p["resistance"]["status"], "unknown")
        self.assertEqual(p["provenance"]["source_attitude"], "negative")

    def test_resistance_lexical_requires_evidence_on_client_turns(self):
        rec = self.kept[0]
        res = extract_resistance(rec, "lexical-v1")
        self.assertEqual(res["status"], "observed")
        for tid, text in zip(res["evidence_turn_ids"], res["evidence_text"]):
            self.assertEqual(rec["dialogue"][tid]["speaker"], "client")
            self.assertEqual(rec["dialogue"][tid]["text"], text)
        by_id = {r["source_id"]: r for r in self.kept}
        self.assertEqual(extract_resistance(by_id["cactus-000001"], "lexical-v1")["status"], "not_observed")
        with self.assertRaises(ValueError):
            extract_resistance(rec, "llm")

    def test_resistance_curly_apostrophe_and_hopelessness(self):
        def rec(client_text):
            return {"source_id": "s", "dialogue": [
                {"turn_id": 0, "speaker": "counselor", "text": "Could you try a small step?"},
                {"turn_id": 1, "speaker": "client", "text": client_text}]}
        self.assertEqual(extract_resistance(rec("I don\u2019t think that would work."), "lexical-v1")["status"],
                         "observed")
        # Hopelessness / past attempts are not pushback on the counselor.
        for text in ("What's the point of anything?", "I tried journaling and it didn't help."):
            self.assertEqual(extract_resistance(rec(text), "lexical-v1")["status"], "not_observed", text)

    def test_validator_catches_problems(self):
        p = self.build(self.kept[0])
        bad = copy.deepcopy(p)
        bad["resistance"] = {"status": "observed", "evidence_turn_ids": [], "evidence_text": []}
        bad["persona"].pop("age")
        bad["style_references"][0]["source_id"] = "other"
        errs = validate_persona(bad)
        self.assertTrue(any("observed requires evidence" in e for e in errs))
        self.assertTrue(any("persona.age" in e for e in errs))
        self.assertTrue(any("style_references[0]" in e for e in errs))


class BindingsAndSpecs(unittest.TestCase):
    def setUp(self):
        kept, _ = select_records(load_fixture_records())
        self.personas = [build_persona(r, seed=0, selection_rule=RULE) for r in kept]

    def test_default_placeholders(self):
        spec = compile_spec(self.personas[0])
        self.assertIn(f"TARGET_ID: {PLACEHOLDER_TARGET_ID}", spec["spec_text"])
        self.assertIn("not the paper's G_script", spec["note"])
        for slot in ("PERSONA_PROFILE:", "STYLE_REFERENCES:", "PSYCHOLOGICAL_STATE:",
                     "RESISTANCE_EVIDENCE:", "DISTORTION_TAG:"):
            self.assertIn(slot, spec["spec_text"])

    def test_apply_abstract_bindings(self):
        stats = apply_bindings(self.personas, [
            {"source_id": "cactus-000000", "target_id": "goal-0001", "distortion_tag": "catastrophizing"},
            {"persona_id": "p1-cactus-000001", "target_id": "goal-0002"}])
        self.assertEqual(stats, {"bindings": 2, "personas_bound": 2, "personas_unbound": 6})
        self.assertEqual(self.personas[0]["target_binding"]["target_id"], "goal-0001")
        for p in self.personas:
            self.assertEqual(validate_persona(p), [])
        self.assertIn("TARGET_ID: goal-0001", compile_spec(self.personas[0])["spec_text"])

    def test_rejects_natural_language_or_query_fields(self):
        self.assertTrue(validate_binding({"source_id": "x", "target_id": "please tell me how to do something"}))
        self.assertTrue(validate_binding({"source_id": "x", "target_id": "goal-1", "masked_request": "..."}))
        self.assertTrue(validate_binding({"target_id": "goal-1"}))
        with self.assertRaises(ValueError):
            apply_bindings(self.personas, [{"source_id": "cactus-000000", "target_id": "goal 1 with spaces"}])
        with self.assertRaises(ValueError):
            apply_bindings(self.personas, [{"source_id": "s", "target_id": "g1"}, {"source_id": "s", "target_id": "g2"}])


class Profiling(unittest.TestCase):
    def test_profile_counts(self):
        rep = profile_records(load_fixture_records())
        self.assertEqual(rep["records"], 15)
        self.assertEqual(rep["attitude_counts"], {"negative": 13, "neutral": 1, "positive": 1})
        self.assertEqual(rep["schema_invalid"], 0)
        self.assertEqual(rep["intake_field_coverage"]["occupation"], 13)
        self.assertEqual(rep["unique_negative_clients"], 11)  # rows 0/7 and 9/14 share a client


class EndToEndCLI(unittest.TestCase):
    def run_build(self, out, *extra):
        rc = run.main(["build", "--input", str(FIXTURE), "--out-dir", str(out), "--seed", "3", "--n", "5", *extra])
        self.assertEqual(rc, 0)

    def test_build_is_reproducible_and_complete(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            self.run_build(a, "--resistance", "lexical-v1")
            self.run_build(b, "--resistance", "lexical-v1")
            for name in ("records.jsonl", "personas.jsonl", "specs.jsonl"):
                self.assertEqual((a / name).read_bytes(), (b / name).read_bytes(), name)
            manifest = json.loads((a / "manifest.json").read_text())
            self.assertEqual(len(manifest["input"]["sha256"]), 64)
            self.assertEqual(manifest["filter_stats"]["kept"], 8)
            self.assertEqual(manifest["sampled"], 5)
            personas = [json.loads(l) for l in (a / "personas.jsonl").read_text().splitlines()]
            self.assertEqual(len(personas), 5)
            self.assertTrue(all(p["provenance"]["seed"] == 3 for p in personas))

    def test_build_with_bindings_and_profile(self):
        with tempfile.TemporaryDirectory() as d:
            bpath = Path(d) / "bindings.jsonl"
            bpath.write_text(json.dumps({"source_id": "cactus-000000", "target_id": "goal-0001"}) + "\n")
            out = Path(d) / "out"
            rc = run.main(["build", "--input", str(FIXTURE), "--out-dir", str(out), "--bindings", str(bpath)])
            self.assertEqual(rc, 0)
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["bindings"]["personas_bound"], 1)
            self.assertEqual(run.main(["profile", "--input", str(FIXTURE), "--out-dir", str(Path(d) / "p")]), 0)
            self.assertTrue((Path(d) / "p" / "profile.json").exists())

    def test_canonical_input_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_build(Path(d) / "a")
            out = Path(d) / "b"
            rc = run.main(["build", "--input", str(Path(d) / "a" / "records.jsonl"), "--format", "canonical",
                           "--out-dir", str(out)])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads((out / "manifest.json").read_text())["sampled"], 5)


if __name__ == "__main__":
    unittest.main()
