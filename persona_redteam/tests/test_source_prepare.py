"""Benign source-preparation tests; no corpus downloads or classifiers."""
import copy
import csv
import io
from pathlib import Path
import tempfile
import unittest

from persona_redteam import source_prepare as source


def conversation(text="A fictional worry.", dataset="hugg_1"):
    return {"inputs": [text, "A fictional follow-up."], "dataset_id": dataset, "label": ""}


def merged(original, label="anxiety_crisis"):
    return {"inputs": list(original["inputs"]), "dataset_id": original["dataset_id"],
            "label": label, "all_labels": [label] * 3}


def vera_fixture():
    fields = ("Name", "Age", "Gender", "Background", "Short Current Suicide Risk Level",
              "Diagnoses and Symptoms", "Current Suicidal Thoughts and Behaviors",
              "Recent Triggers and Stressors", "Primary Communication Style", "Reaction to Chatbot Responses")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    index = 0
    for risk, count in source.VERA_COUNTS.items():
        for _ in range(count):
            row = dict.fromkeys(fields, "fictional fixture")
            row.update(Name=f"fixture-{index}", **{"Short Current Suicide Risk Level": risk})
            writer.writerow(row)
            index += 1
    return stream.getvalue().encode()


class SourcePreparationTests(unittest.TestCase):
    def test_vera_schema_and_risk_counts(self):
        report = source.validate_vera(vera_fixture())
        self.assertEqual(report["rows"], 100)
        self.assertEqual(report["unique_names"], 100)
        self.assertEqual(report["risk_counts"], source.VERA_COUNTS)

    def test_vera_invalid_schema_and_counts(self):
        with self.assertRaises(ValueError):
            source.validate_vera(b"Name\tAge\nfixture\t30\n")
        data = vera_fixture().replace(b"fixture-1\t", b"fixture-0\t")
        with self.assertRaises(ValueError):
            source.validate_vera(data)

    def test_source_hash_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "jmir_test.json").write_text("[]")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                source.read_source(directory, "jmir_test.json")

    def test_positional_join_preserves_source_text_and_ids(self):
        a, b = conversation(" leading space\nand trailing space "), conversation("Another message.")
        test, labels = [a, b], [merged(a), merged(b, "no_crisis")]
        saved = copy.deepcopy((test, labels))
        rows = source.reconstruct_jmir(test, labels)
        self.assertEqual(len({r["goal_id"] for r in rows}), 2)
        self.assertEqual([r["source_row_index"] for r in rows], [0, 1])
        self.assertEqual(rows[0]["inputs"], a["inputs"])
        self.assertEqual(rows[0]["goal"], "\n".join(a["inputs"]))
        self.assertEqual(rows[0]["dataset_id"], a["dataset_id"])
        self.assertEqual((test, labels), saved)

    def test_reordered_labels_are_rejected(self):
        a, b = conversation("One."), conversation("Two.")
        with self.assertRaisesRegex(ValueError, "alignment mismatch"):
            source.reconstruct_jmir([a, b], [merged(b), merged(a)])

    def test_duplicate_composite_key_is_not_silently_merged(self):
        a = conversation()
        with self.assertRaisesRegex(ValueError, "duplicate composite"):
            source.reconstruct_jmir([a, a], [merged(a), merged(a)])

    def test_missing_and_unknown_merged_labels_are_rejected(self):
        a = conversation()
        invalid = merged(a)
        invalid.pop("label")
        with self.assertRaises(ValueError):
            source.reconstruct_jmir([a], [invalid])
        with self.assertRaises(ValueError):
            source.reconstruct_jmir([a], [merged(a, "invented")])

    def test_invalid_input_schema_is_rejected(self):
        for value in (None, "a string", [1], []):
            a = conversation()
            a["inputs"] = value
            with self.assertRaises(ValueError):
                source.reconstruct_jmir([a], [merged(conversation())])
        with self.assertRaises(ValueError):
            source.reconstruct_jmir([conversation()], [])

    def test_crisis_filter_only_removes_no_crisis_and_missing(self):
        labels = ["anxiety_crisis", "no_crisis", None, "", "self-harm"]
        test = [conversation(f"Fictional {i}.") for i in range(len(labels))]
        rows = source.reconstruct_jmir(test, [merged(a, label) for a, label in zip(test, labels)])
        subset = source.crisis_subset(rows)
        self.assertEqual(subset, [rows[0], rows[4]])
        self.assertIs(subset[0], rows[0])
        self.assertNotIn("is_client_utterance", subset[0])

    def test_deterministic_serialization_and_newlines(self):
        a = conversation("Fictional café.")
        rows = source.reconstruct_jmir([a], [merged(a)])
        data = source.jsonl_bytes(rows)
        self.assertEqual(data, source.jsonl_bytes(source.reconstruct_jmir([a], [merged(a)])))
        self.assertIn("café".encode(), data)
        self.assertTrue(data.endswith(b"\n"))
        self.assertNotIn(b"\r\n", data)

    def test_manifest_mismatch_is_reported_without_tuning(self):
        report = source.compare_manifest({"rows": 1, "bytes": 10, "sha256": "actual"},
                                         {"rows": 1, "bytes": 20, "sha256": "expected"})
        self.assertEqual(set(report), {"bytes", "sha256"})

    def test_write_once_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.tsv"
            source.write_once(path, b"unchanged")
            source.write_once(path, b"unchanged")
            with self.assertRaises(ValueError):
                source.write_once(path, b"different")
            self.assertEqual(path.read_bytes(), b"unchanged")

    def test_source_dataset_counts_recover_duplicate_source_aliases(self):
        a, b = conversation("A.", "hugg_2"), conversation("B.", "hugg_6")
        rows = source.reconstruct_jmir([a, b], [merged(a), merged(b)])
        report = source.summarize(rows, source.jsonl_bytes(rows))
        self.assertEqual(report["source_hf_counts"], {"marmikpandya/mental-health": 2})
        self.assertEqual(report["source_dataset_counts"], {"hugg_2": 1, "hugg_6": 1})


if __name__ == "__main__":
    unittest.main()
