"""Offline synthetic tests; no corpus sampling results or model inferences."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from persona_redteam import phase1_reproduce as phase1
from persona_redteam.phase1_builder import build_messages, validate_build
from persona_redteam.tests.synthetic_inputs import write_inputs


def fixture(root):
    import csv
    write_inputs(root)
    with (root / "personas/veramh_si_n100.tsv").open(newline="") as stream:
        vera = list(csv.DictReader(stream, delimiter="\t"))
    for row in vera:
        for key in ("Diagnoses and Symptoms", "Current Suicidal Thoughts and Behaviors",
                    "Recent Triggers and Stressors", "Primary Communication Style"):
            row[key] = "Fictional benign test information."
    return (phase1.read_jsonl(root / "goals/crisis_goals_jmir_client.jsonl"), vera,
            phase1.read_jsonl(root / "personas/cactus_distress_n2000.jsonl"))


class FakeAPI:
    """Transport fixture, never a production fallback or semantic evaluator."""
    def __init__(self, accept=True):
        self.calls = []
        self.accept = accept

    def __call__(self, operation, body):
        self.calls.append((operation, deepcopy(body)))
        if operation == "embeddings":
            return {"model": body["model"], "data": [
                {"index": i, "embedding": [1.0, 0.5]} for i, _ in enumerate(body["input"])],
                "usage": {"prompt_tokens": 1, "total_tokens": 1}}
        system = body["messages"][0]["content"]
        if system == phase1.CLIENT_SYSTEM:
            value = {"is_client_utterance": "yes" if self.accept else "no", "is_request": "yes"}
        elif system == phase1.PATHOLOGY_SYSTEM:
            value = {"core_condition": "Fictional exam worry", "distortions": ["fixture-label"],
                     "keywords": ["exam"], "compliance_lever": "benign test marker", "risk_needed": "Low"}
        else:
            goal = json.loads(body["messages"][1]["content"])["goal_context"]["goal"]
            value = {"injected_belief": "This is a hypothetical belief about fictional examination worry.",
                     "target_evidence": [{"field": "goal", "start": 0, "end": len(goal), "text": goal}],
                     "client_turns": ["I am feeling worried about my upcoming examination.",
                                      "I would like some support with my study schedule."]}
        return {"model": body["model"], "id": "fixture-response", "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(value)}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}}


class Phase1ReproductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.goals, self.vera, self.cactus = fixture(self.root)

    def cache(self, api=None, budget=100):
        return phase1.RequestCache(self.root / "run", "fixture-fingerprint", api, budget)

    def test_client_module_import_has_no_environment_or_network_side_effect(self):
        from persona_redteam.goals import filter_client_utterances
        with patch.dict("os.environ", {}, clear=True), patch("urllib.request.urlopen", side_effect=AssertionError):
            importlib.reload(filter_client_utterances)

    def test_pilot_uses_original_order_first_per_label(self):
        selected = phase1.select_pilot(self.goals, 1)
        self.assertEqual([r["goal_id"] for r in selected], [r["goal_id"] for r in self.goals[::2]])
        self.assertEqual(phase1.select_pilot(self.goals, 0), self.goals)

    def test_invalid_pilot_and_duplicates_are_rejected(self):
        for rows, n in ((self.goals, -1), (self.goals + self.goals[:1], 2)):
            with self.assertRaises(ValueError):
                phase1.select_pilot(rows, n)

    def test_run_outputs_are_restricted_to_ignored_repository_directory(self):
        with self.assertRaises(ValueError):
            phase1.run_directory(phase1.ROOT / "tests/forbidden-output")
        self.assertEqual(phase1.run_directory(phase1.ROOT / "outputs/test-plan"),
                         phase1.ROOT / "outputs/test-plan")

    def test_default_run_only_plans(self):
        with patch.object(phase1, "load_run", return_value={}), patch.object(phase1, "plan", return_value={"offline": True}), patch.object(phase1, "api_transport", side_effect=AssertionError):
            # Use the required output namespace without creating files there.
            self.assertEqual(phase1.run(phase1.ROOT / "outputs/test-plan"), {"offline": True})

    def test_real_transport_requires_key_and_known_operation(self):
        with patch.dict("os.environ", {}, clear=True), patch("urllib.request.urlopen", side_effect=AssertionError):
            with self.assertRaises(RuntimeError):
                phase1.api_transport("chat/completions", {})
            with self.assertRaises(ValueError):
                phase1.api_transport("unapproved", {})

    def test_complete_synthetic_pipeline_preserves_ids_text_and_routes(self):
        api = FakeAPI()
        cache = self.cache(api)
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            result = phase1.pipeline(self.goals, self.vera, self.cactus, cache, self.root / "run", synthetic=True)
        self.assertEqual(result["built_personas"], 12)
        self.assertEqual(result["candidate_links"], 36)
        self.assertEqual(result["target_model_calls"], 0)
        self.assertEqual(result["phase2_calls"], 0)
        self.assertEqual(result["status"], "synthetic_software_validation")
        builds = phase1.read_jsonl(self.root / "run/phase1_personas.jsonl")
        for goal, built in zip(self.goals, builds):
            self.assertEqual(built["goal_id"], goal["goal_id"])
            self.assertEqual(built["goal"], goal["goal"])
            expected = "VERA-SI" if goal["crisis_label"] in ("suicidal_ideation", "self-harm") else "Cactus"
            self.assertEqual(built["source"], expected)
            self.assertTrue(built["synthetic_test_only"])
            self.assertFalse(built["historical_reproduction"])
        before = len(api.calls)
        replay = phase1.pipeline(self.goals, self.vera, self.cactus, self.cache(api), self.root / "run", synthetic=True)
        self.assertEqual(result, replay)
        self.assertEqual(len(api.calls), before)

    def test_all_excluded_makes_no_embedding_or_builder_requests(self):
        api = FakeAPI(accept=False)
        report = phase1.pipeline(self.goals, self.vera, self.cactus, self.cache(api), self.root / "run", synthetic=True)
        self.assertEqual(report["built_personas"], 0)
        self.assertEqual(len(api.calls), 12)
        self.assertEqual(report["excluded"], 12)

    def test_filter_error_is_not_silently_counted_as_exclusion(self):
        class BadCache:
            def chat(self, *args):
                return {"is_client_utterance": None, "is_request": "yes"}
        with self.assertRaisesRegex(ValueError, "errors are not exclusions"):
            phase1.pipeline(self.goals, self.vera, self.cactus, BadCache(), self.root / "run")
        self.assertFalse((self.root / "run/client_goals.jsonl").exists())

    def test_upstream_400_character_classifier_input_is_preserved(self):
        api = FakeAPI(accept=False)
        goal = {**self.goals[0], "goal": "x" * 600}
        phase1.pipeline([goal], self.vera, self.cactus, self.cache(api), self.root / "run", synthetic=True)
        self.assertEqual(api.calls[0][1]["messages"][1]["content"], "x" * 400)
        self.assertEqual(phase1.read_jsonl(self.root / "run/client_decisions.jsonl")[0]["goal"], "x" * 600)

    def test_request_budget_stops_before_sending_or_recording_attempt(self):
        api = FakeAPI()
        with self.assertRaisesRegex(RuntimeError, "budget"):
            self.cache(api, 0).request("fixture", "embeddings", {})
        self.assertEqual(api.calls, [])
        self.assertFalse((self.root / "run/requests").exists())

    def test_uncertain_request_is_not_automatically_retried(self):
        calls = []
        def failure(*args):
            calls.append(args)
            raise TimeoutError("fixture timeout")
        cache = self.cache(failure)
        with self.assertRaisesRegex(RuntimeError, "no automatic retry"):
            cache.request("fixture", "embeddings", {})
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            cache.request("fixture", "embeddings", {})
        self.assertEqual(len(calls), 1)

    def test_request_budget_includes_attempts_before_restart(self):
        api = FakeAPI()
        self.cache(api, 1).embed(["first"])
        resumed = self.cache(api, 1)
        resumed.embed(["first"])
        with self.assertRaisesRegex(RuntimeError, "request budget"):
            resumed.embed(["second"])
        self.assertEqual(len(api.calls), 1)

    def test_one_time_key_is_hidden_cleared_and_not_exported(self):
        key = phase1.OneTimeKey()
        with patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", return_value="fixture-secret"), patch.dict("os.environ", {}, clear=True), patch.object(phase1, "api_transport", return_value={}) as transport:
            key.read()
            self.assertEqual(key("embeddings", {}), {})
            transport.assert_called_once_with("embeddings", {}, api_key="fixture-secret")
            self.assertNotIn("fixture-secret", repr(key))
            key.clear()
            self.assertIsNone(key._key)
            import os
            self.assertNotIn("OPENAI_API_KEY", os.environ)

    def test_noninteractive_input_is_rejected_without_prompt(self):
        with patch("sys.stdin.isatty", return_value=False), patch("getpass.getpass") as prompt:
            with self.assertRaisesRegex(RuntimeError, "TTY"):
                phase1.OneTimeKey().read()
            prompt.assert_not_called()

    def test_run_clears_key_after_success_and_pipeline_error(self):
        import csv
        for fails in (False, True):
            with self.subTest(fails=fails):
                directory = self.root / "outputs" / str(fails)
                directory.mkdir(parents=True)
                with (directory / "vera.tsv").open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(self.vera[0]), delimiter="\t")
                    writer.writeheader()
                    writer.writerows(self.vera)
                (directory / "pilot_goals.jsonl").write_bytes(phase1.source.jsonl_bytes(self.goals))
                (directory / "cactus_candidates.jsonl").write_bytes(phase1.source.jsonl_bytes(self.cactus))
                key = phase1.OneTimeKey()
                def read():
                    key._key = "fixture-secret"
                def pipeline(*args):
                    self.assertEqual(key._key, "fixture-secret")
                    if fails:
                        raise ValueError("fixture error")
                    return {"fixture": True}
                with patch.object(phase1, "ROOT", self.root), patch.object(phase1, "load_run", return_value={"counts": {"pilot": 12}}), patch.object(phase1, "OneTimeKey", return_value=key), patch.object(key, "read", side_effect=read), patch.object(phase1, "pipeline", side_effect=pipeline):
                    if fails:
                        with self.assertRaises(ValueError):
                            phase1.run(directory, True, 54, 0.25, True)
                    else:
                        self.assertEqual(phase1.run(directory, True, 54, 0.25, True), {"fixture": True})
                self.assertIsNone(key._key)
                for path in directory.rglob("*.json"):
                    self.assertNotIn("fixture-secret", path.read_text())

    def test_privacy_guard_stops_before_checkpoint_or_network(self):
        api = FakeAPI()
        for text in ("person@example.org", "Name: Example", "555-123-4567", "sk-" + "x" * 20):
            with self.assertRaisesRegex(ValueError, "privacy"):
                self.cache(api).embed([text])
        self.assertEqual(api.calls, [])
        self.assertFalse((self.root / "run/requests").exists())

    def test_failure_logs_do_not_include_exception_secret(self):
        def failure(*args):
            raise RuntimeError("fixture-secret-do-not-log")
        cache = self.cache(failure)
        with self.assertRaisesRegex(RuntimeError, "no automatic retry") as raised:
            cache.embed(["fixture"])
        self.assertNotIn("fixture-secret", str(raised.exception))
        for path in cache.directory.iterdir():
            self.assertNotIn("fixture-secret", path.read_text())
        self.assertEqual(phase1.usage_report(cache.directory)["failed_or_uncertain"], 1)

    def test_usage_cost_is_derived_from_response_tokens(self):
        cache = self.cache(FakeAPI())
        cache.embed(["fixture"])
        cache.chat("client_filter", [{"role": "system", "content": phase1.CLIENT_SYSTEM}], 30)
        report = phase1.usage_report(cache.directory)
        self.assertEqual(report["total_attempts"], 2)
        self.assertEqual(report["failed_or_uncertain"], 0)
        self.assertAlmostEqual(report["estimated_cost_from_reported_tokens_usd"], (0.02 + 2 * 0.15 + 3 * 0.60) / 1_000_000)

    def test_cost_budget_applies_across_restarts(self):
        api = FakeAPI()
        cache = phase1.RequestCache(self.root / "run", "fixture-fingerprint", api, 10, 0.000001)
        cache.embed(["first"])
        previous = cache.reserved_cost
        resumed = phase1.RequestCache(self.root / "run", "fixture-fingerprint", api, 10, 0.000001)
        self.assertEqual(resumed.reserved_cost, previous)
        with self.assertRaisesRegex(RuntimeError, "cost budget"):
            resumed.embed(["too long " * 100])
        self.assertEqual(len(api.calls), 1)

    def test_cache_key_includes_exact_request_body(self):
        api = FakeAPI()
        cache = self.cache(api)
        cache.embed(["first"])
        cache.embed(["second"])
        cache.embed(["first"])
        self.assertEqual(len(api.calls), 2)

    def test_tampered_cached_response_is_rejected(self):
        api = FakeAPI()
        cache = self.cache(api)
        cache.embed(["first"])
        path = next(cache.directory.glob("*.response.json"))
        value = json.loads(path.read_text())
        value["response"]["data"][0]["embedding"] = [99, 99]
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "response hash"):
            cache.embed(["first"])

    def test_run_manifest_detects_changed_input_and_code(self):
        root = self.root / "fake_repo"
        run = root / "outputs/run"
        run.mkdir(parents=True)
        (root / "module.py").write_text("original")
        (run / "goals.jsonl").write_text("{}\n")
        manifest = {"mode": phase1.MODE, "models": phase1.MODELS,
                    "payloads": {"goals.jsonl": {"sha256": phase1.cactus.sha256(run / "goals.jsonl")}},
                    "code_sha256": {"module.py": phase1.cactus.sha256(root / "module.py")}}
        (run / "manifest.json").write_text(json.dumps(manifest))
        with patch.object(phase1, "ROOT", root), patch.object(phase1, "CODE_FILES", ("module.py",)):
            self.assertEqual(phase1.load_run(run), manifest)
            (root / "module.py").write_text("changed")
            with self.assertRaisesRegex(ValueError, "code changed"):
                phase1.load_run(run)
            (root / "module.py").write_text("original")
            (run / "goals.jsonl").write_text("changed")
            with self.assertRaisesRegex(ValueError, "input hash"):
                phase1.load_run(run)

    def test_refusal_or_truncation_does_not_become_persona(self):
        def truncated(*args):
            return {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}
        with self.assertRaisesRegex(ValueError, "truncated"):
            self.cache(truncated).chat("builder", [], 900)

    def test_embedding_count_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            self.cache(lambda *a: {"data": []}).embed(["fixture"])

    def test_invalid_pathology_is_rejected(self):
        with self.assertRaises(ValueError):
            phase1.checked_pathology({})

    def test_matcher_filters_risk_and_preserves_stable_tie_order(self):
        goal = {**self.goals[0], "pathology": {}}
        routed = phase1.rank_candidates([goal], self.vera, self.cactus,
                  [[1, 0]] * len(self.vera), [[1, 0]] * len(self.cactus), [[1, 0]])
        self.assertEqual([c["id"] for c in routed[0]["persona_candidates"]], ["fixture-v1", "fixture-v2", "fixture-v3"])

    def test_matcher_rejects_dimension_nan_and_zero_vectors(self):
        for vector in ([1], [float("nan"), 0], [0, 0]):
            with self.assertRaises(ValueError):
                phase1.rank_candidates([{**self.goals[0], "pathology": {}}], self.vera, self.cactus,
                    [[1, 0]] * len(self.vera), [[1, 0]] * len(self.cactus), [vector])

    def test_builder_uses_first_candidate_and_original_fields(self):
        case = {"goal": self.goals[0], "pathology": {"keywords": ["fixture"]}, "candidates": [
            {"candidate": {"source": "Cactus"}, "persona": self.cactus[0]},
            {"candidate": {"source": "Cactus"}, "persona": {"descriptor": "SHOULD_NOT_APPEAR"}}]}
        messages = build_messages(case)
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["original_objective"], self.goals[0]["goal"])
        self.assertIn(self.cactus[0]["style_reference"], payload["persona_context"])
        self.assertNotIn("SHOULD_NOT_APPEAR", payload["persona_context"])

    def test_builder_rejects_placeholder_turns(self):
        with self.assertRaises(ValueError):
            validate_build({"persona_summary": "word " * 30, "client_turns": ["t1", "t2"]})


if __name__ == "__main__":
    unittest.main()
