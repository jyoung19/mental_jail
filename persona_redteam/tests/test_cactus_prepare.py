"""Benign offline preprocessing/lineage tests; no historical ranking fixture."""
import copy
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from persona_redteam import cactus_prepare as cactus


def row(thought="I worry about an exam.", attitude="negative"):
    return {"thought": thought, "patterns": ["overgeneralization"],
            "intake_form": "Name:\nFictional Person\nAge:\n30\nGender: Not specified\n"
                           "Occupation: Undisclosed\n2. Presenting Problem\nExam worry.\n"
                           "3. Reason for Seeking Counseling\nI want support.\n4. Past History\nNone.",
            "dialogue": "Counselor: Welcome.\nClient: I feel worried about an exam.",
            "attitude": attitude, "cbt_technique": "fictional technique", "cbt_plan": "fictional plan"}


class CactusPreparationTests(unittest.TestCase):
    def test_raw_schema(self):
        cactus.validate_schema([row()])
        for field in cactus.FIELDS:
            with self.subTest(field=field):
                invalid = row()
                invalid.pop(field)
                with self.assertRaises(ValueError):
                    cactus.validate_schema([invalid])

    def test_raw_schema_types(self):
        for change in ({"patterns": "a"}, {"patterns": [1]}, {"thought": None},
                       {"thought": " "}, {"attitude": "invented"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                cactus.validate_schema([{**row(), **change}])
        for value in ({}, [None]):
            with self.assertRaises(ValueError):
                cactus.validate_schema(value)

    def test_hash_gate_precedes_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.json"
            path.write_text("[]")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                cactus.load_pinned_raw(path)

    def test_pinned_count_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.json"
            path.write_text(json.dumps([row()]))
            with patch.object(cactus, "RAW_SHA256", cactus.sha256(path)):
                with self.assertRaisesRegex(ValueError, "counts mismatch"):
                    cactus.load_pinned_raw(path)

    def test_normalization_preserves_case_and_punctuation(self):
        self.assertEqual(cactus.normalize_thought("  I\tworry.\n "), "I worry.")
        self.assertNotEqual(cactus.normalize_thought("I worry."), "i worry.")
        self.assertNotEqual(cactus.normalize_thought("I worry."), "I worry")

    def test_duplicate_handling_retains_all_source_indices(self):
        candidates, report = cactus.prepare_candidates([row("I worry."), row(" I  worry. ")])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source_row_index"], 0)
        self.assertEqual(candidates[0]["duplicate_source_row_indices"], [0, 1])
        self.assertEqual(candidates[0]["thought"], "I worry.")
        self.assertEqual(report["exact_unique_negative_thoughts"], 2)
        self.assertEqual(report["duplicate_negative_rows"], 1)

    def test_negative_filter_before_dedup(self):
        candidates, report = cactus.prepare_candidates([row(attitude="positive"), row(), row(attitude="neutral")])
        self.assertEqual(candidates[0]["source_row_index"], 1)
        self.assertEqual(report["raw_rows"], 3)
        self.assertEqual(report["negative_rows"], 1)

    def test_deterministic_without_mutating_input(self):
        rows = [row(), row("Another worry.")]
        original = copy.deepcopy(rows)
        self.assertEqual(json.dumps(cactus.prepare_candidates(rows), sort_keys=True),
                         json.dumps(cactus.prepare_candidates(rows), sort_keys=True))
        self.assertEqual(rows, original)

    def test_placeholder_and_source_section_handling(self):
        candidate = cactus.prepare_candidates([row()])[0][0]
        self.assertEqual(candidate["intake"]["age"], "30")
        self.assertIsNone(candidate["intake"]["gender"])
        self.assertIsNone(candidate["intake"]["occupation"])
        self.assertEqual(candidate["condition"], "Exam worry.")
        self.assertEqual(candidate["intake"]["reason_for_seeking_help"], "I want support.")
        self.assertEqual(candidate["background"], row()["intake_form"])
        self.assertIsNone(candidate["distress_tags"])
        self.assertIsNone(candidate["resistance"])
        for placeholder in ("Not specified", "Undisclosed", "N/A", "unknown"):
            self.assertIsNone(cactus.clean_value(placeholder))

    def test_empty_occupation_does_not_swallow_next_field(self):
        self.assertIsNone(cactus.intake_fields("Occupation:\nEducation: College")["occupation"])

    def test_qualified_client_labels_and_downstream_ids(self):
        for qualifier in ("sighs", "sarcastically"):
            with self.subTest(qualifier=qualifier):
                turns = cactus.parse_dialogue(f"Counselor: Hi.\nClient ({qualifier}): Hello.\nCounselor: Welcome.")
                self.assertEqual([t["speaker"] for t in turns], ["counselor", "client", "counselor"])
                self.assertEqual(turns[1]["text"], f"({qualifier}) Hello.")
                self.assertEqual([t["turn_id"] for t in turns], [0, 1, 2])

    def test_qualified_counselor_and_true_continuation(self):
        turns = cactus.parse_dialogue("Counselor (gently): First line\nsecond line\nClient: Hello.")
        self.assertEqual(turns[0]["text"], "(gently) First line second line")
        self.assertEqual(turns[0]["speaker"], "counselor")
        self.assertEqual(turns[1]["turn_id"], 1)

    def test_unknown_speaker_remains_continuation(self):
        turns = cactus.parse_dialogue("Client: Hello.\nObserver (quietly): Note.")
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["text"], "Hello. Observer (quietly): Note.")

    def test_candidate_preserves_full_thought_style_and_pattern_order(self):
        raw = row("A fictional worry. " * 20)
        raw["patterns"] = ["mental filtering", "overgeneralization", "none"]
        text = "A fictional client sentence. " * 20
        raw["dialogue"] = "Counselor: Hi.\nClient: " + text
        candidate = cactus.prepare_candidates([raw])[0][0]
        self.assertEqual(candidate["thought"], raw["thought"])
        self.assertEqual(candidate["style_reference"], " ".join(text.split()))
        self.assertGreater(len(candidate["thought"]), 200)
        self.assertGreater(len(candidate["style_reference"]), 200)
        self.assertEqual(candidate["patterns"], raw["patterns"])

    def test_current_main_loaders_accept_candidate_schema_without_api_calls(self):
        root = Path(__file__).resolve().parents[1]

        def load_module(name, relative):
            spec = importlib.util.spec_from_file_location(name, root / relative)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        embeddings = types.ModuleType("embeddings")
        embeddings.embed_texts = Mock(side_effect=AssertionError("embeddings must not be called"))
        with tempfile.TemporaryDirectory() as directory:
            isolated = Path(directory)
            (isolated / "personas").mkdir()
            candidates = cactus.prepare_candidates([row(), row("Another fictional worry.")])[0]
            (isolated / "personas/cactus_distress_n2000.jsonl").write_text(
                "\n".join(json.dumps(p) for p in candidates) + "\n")
            fields = ("Age", "Gender", "Diagnoses and Symptoms", "Current Suicidal Thoughts and Behaviors",
                      "Recent Triggers and Stressors", "Primary Communication Style")
            with (isolated / "personas/veramh_si_n100.tsv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
                writer.writeheader()
                writer.writerow(dict.fromkeys(fields, "fictional fixture"))
            with patch.dict(sys.modules, {"embeddings": embeddings}), patch(
                    "urllib.request.urlopen", side_effect=AssertionError("network must not be called")) as network:
                extraction = load_module("fixture_extraction", "extraction/extract_persona_pathology.py")
                matching = load_module("fixture_matching", "matching/match_pathology.py")
                with patch.object(extraction, "ROOT", isolated), patch.object(matching, "ROOT", isolated):
                    extracted = extraction.load_source("cactus")
                    vera, vera_texts, loaded, texts = matching.load_pools()
                self.assertEqual([item[0] for item in extracted], [p["persona_id"] for p in candidates])
                self.assertTrue(all(item[1] == "Cactus" and isinstance(item[2], str) and item[3] is None
                                    for item in extracted))
                self.assertEqual(loaded, candidates)
                self.assertEqual(len(texts), 2)
                self.assertEqual(len(vera), len(vera_texts))
                network.assert_not_called()
                embeddings.embed_texts.assert_not_called()

    def artifact_report(self, artifact, rows=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "historical.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in artifact) + "\n")
            expected = {"sha256": cactus.sha256(path), "bytes": path.stat().st_size, "rows": len(artifact)}
            return cactus.validate_artifact(path, rows or [row()], expected)

    def test_historical_validator_synthetic_fixture(self):
        candidate = cactus.prepare_candidates([row()])[0][0]
        artifact = {k: candidate[k] for k in cactus.PERSONA_FIELDS}
        artifact["persona_id"] = "historical-fixture"
        report = self.artifact_report([artifact])
        self.assertTrue(all(report["integrity_matches"].values()))
        self.assertTrue(report["every_row_in_candidate_pool"])
        self.assertEqual(report["unique_persona_ids"], 1)
        self.assertEqual(report["mapping"][0]["selected_source_row_id"], "cactus-000000")
        self.assertEqual(report["mapping"][0]["unmapped_fields"], ["persona_id", "distress_tags", "resistance"])
        self.assertEqual(report["selected_thought_order"], [row()["thought"]])
        self.assertEqual(report["selected_raw_thought_order"], [row()["thought"]])

    def test_historical_validator_conflicting_source_index_is_not_recovered(self):
        report = self.artifact_report([{"persona_id": "x", "thought": row()["thought"], "source_row_index": 99}])
        self.assertTrue(report["every_row_in_candidate_pool"])
        self.assertIsNone(report["mapping"][0]["selected_source_row_id"])
        self.assertEqual(report["mapping"][0]["jointly_supported_source_row_indices"], [])
        self.assertIn("source_row_index", report["mapping"][0]["unmapped_fields"])

    def test_historical_validator_reports_integrity_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.jsonl"
            path.write_text(json.dumps({"persona_id": "x", "thought": row()["thought"]}) + "\n")
            report = cactus.validate_artifact(path, [row()])
            self.assertFalse(any(report["integrity_matches"].values()))

    def test_historical_validator_ambiguity_and_duplicate_ids(self):
        report = self.artifact_report([{"persona_id": "same", "thought": row()["thought"]}] * 2, [row(), row()])
        self.assertEqual(report["duplicate_persona_ids"], 1)
        self.assertIsNone(report["mapping"][0]["selected_source_row_id"])
        self.assertEqual(report["mapping"][0]["possible_source_row_indices"], [0, 1])

    def test_historical_validator_unmapped_fields_and_foreign_thought(self):
        report = self.artifact_report([{"persona_id": "x", "thought": "Not in source.", "extra": None}])
        self.assertFalse(report["every_row_in_candidate_pool"])
        self.assertIn("extra", report["mapping"][0]["unmapped_fields"])
        self.assertEqual(report["mapping"][0]["jointly_supported_source_row_indices"], [])

    def test_historical_validator_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            report = cactus.validate_artifact(Path(directory) / "absent.jsonl", [row()])
            self.assertEqual(report["status"], "missing")


if __name__ == "__main__":
    unittest.main()
