"""Unit tests for the pure logic in potatollm.

Nothing here talks to Ollama or reads real memory counters: every function
that would is patched, so the suite runs the same on a laptop and in CI.
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import potatollm as p


class ClassifyFitTests(unittest.TestCase):
    def test_boundaries(self):
        # ratio = size / total; the thresholds are inclusive on the safe side.
        self.assertEqual(p.classify_fit(10, 5, 2.2), "fits comfortably")
        self.assertEqual(p.classify_fit(10, 5, 2.3), "tight fit")
        self.assertEqual(p.classify_fit(10, 5, 3.5), "tight fit")
        self.assertEqual(p.classify_fit(10, 5, 3.6), "will page")
        self.assertEqual(p.classify_fit(10, 5, 5.0), "will page")
        self.assertEqual(p.classify_fit(10, 5, 5.1), "do not try")

    def test_unknown_inputs(self):
        self.assertEqual(p.classify_fit(p.UNKNOWN, 5, 2), p.UNKNOWN)
        self.assertEqual(p.classify_fit(8, 5, None), p.UNKNOWN)
        self.assertEqual(p.classify_fit(0, 5, 2), p.UNKNOWN)

    def test_every_verdict_is_listed(self):
        seen = {p.classify_fit(10, 5, size) for size in (1, 3, 4.5, 9)}
        self.assertEqual(seen, set(p.VERDICTS))


class ModelNameTests(unittest.TestCase):
    def test_split_model(self):
        self.assertEqual(p.split_model("qwen3:4b"), ("qwen3", "4b"))
        self.assertEqual(p.split_model("qwen3"), ("qwen3", "latest"))
        self.assertEqual(p.split_model("qwen3:"), ("qwen3", "latest"))
        self.assertEqual(p.split_model(" llama3 : 8b "), ("llama3", "8b"))

    def test_model_match(self):
        self.assertTrue(p.model_match("qwen3:4b", "qwen3:4b"))
        self.assertTrue(p.model_match("QWEN3:4B", "qwen3:4b"))
        self.assertTrue(p.model_match("qwen3:latest", "qwen3"))
        self.assertTrue(p.model_match("qwen3:4b", "qwen3"))
        # A bare name must not swallow a different model that shares a prefix.
        self.assertFalse(p.model_match("qwen3-coder:4b", "qwen3"))
        self.assertFalse(p.model_match("qwen3:8b", "qwen3:4b"))

    def test_result_filename_sanitises_model(self):
        name = p.result_filename("hf.co/user/model:Q4_K_M").name
        self.assertTrue(name.endswith("-hf.co_user_model_Q4_K_M.json"))
        self.assertNotIn("/", name)
        self.assertNotIn(":", name)


class ParsingTests(unittest.TestCase):
    def test_parse_size_to_gb(self):
        self.assertEqual(p.parse_size_to_gb("4.7GB"), 4.7)
        self.assertEqual(p.parse_size_to_gb("934MB"), 0.912)
        self.assertEqual(p.parse_size_to_gb("2 GiB"), 2.0)
        self.assertEqual(p.parse_size_to_gb(""), p.UNKNOWN)
        self.assertEqual(p.parse_size_to_gb("no sizes here"), p.UNKNOWN)

    def test_parse_size_prefers_plausible_artifact_sizes(self):
        # 900 GB is page boilerplate, not a model; 0.01 GB is too small to be one.
        self.assertEqual(p.parse_size_to_gb("900 GB traffic, model 2.5GB, 0.01 GB icon"), 2.5)
        # With nothing plausible, fall back to the largest number seen.
        self.assertEqual(p.parse_size_to_gb("0.01 GB"), 0.01)

    def test_parse_quantization(self):
        self.assertEqual(p.parse_quantization("", "qwen2.5:1.5b-instruct-q4_K_M"), "Q4_K_M")
        self.assertEqual(p.parse_quantization("quantization Q8_0", "qwen3:4b"), "Q8_0")
        self.assertEqual(p.parse_quantization("", "llama3:8b-fp16"), "FP16")
        self.assertEqual(p.parse_quantization("", ""), p.UNKNOWN)
        # The model name wins over the page text.
        self.assertEqual(p.parse_quantization("Q8_0 everywhere", "model:q4_0"), "Q4_0")

    def test_unit_helpers(self):
        self.assertEqual(p.bytes_to_gb(1024 ** 3), 1.0)
        self.assertEqual(p.bytes_to_gb("x"), p.UNKNOWN)
        self.assertEqual(p.bytes_to_gb(None), p.UNKNOWN)
        self.assertEqual(p.gb_to_bytes(1), 1024 ** 3)
        self.assertIsNone(p.gb_to_bytes("x"))
        self.assertEqual(p.human_gb(1.5), "1.50 GB")
        self.assertEqual(p.human_gb(None), p.UNKNOWN)
        self.assertIsNone(p.safe_float(p.UNKNOWN))
        self.assertEqual(p.safe_float("2.5"), 2.5)


class WarningTests(unittest.TestCase):
    def test_ram_free_warning(self):
        self.assertIn("close programs", p.ram_free_warning(0.5, 2))
        self.assertIsNone(p.ram_free_warning(5, 2))
        self.assertIsNone(p.ram_free_warning(p.UNKNOWN, 2))
        # Threshold grows with the model (0.75 * size + 0.5) but caps at 2.5 GB.
        self.assertIsNotNone(p.ram_free_warning(1.9, 2))
        self.assertIsNone(p.ram_free_warning(2.1, 2))
        self.assertIsNotNone(p.ram_free_warning(2.4, 40))
        self.assertIsNone(p.ram_free_warning(2.6, 40))
        # Without a model size the floor is 1 GB.
        self.assertIsNotNone(p.ram_free_warning(0.9, None))
        self.assertIsNone(p.ram_free_warning(1.1, None))

    def test_suggest_smaller(self):
        self.assertEqual(p.suggest_smaller("qwen3:8b", "fits comfortably"), "none")
        with mock.patch.object(p, "get_local_model_names", return_value=["qwen3:4b", "qwen3:8b"]):
            self.assertEqual(p.suggest_smaller("qwen3:8b", "will page"), "qwen3:4b")
        with mock.patch.object(p, "get_local_model_names", return_value=[]):
            self.assertEqual(p.suggest_smaller("qwen3:8b", "do not try"), "try a 3B or smaller quantized model")
        with mock.patch.object(p, "get_local_model_names", side_effect=p.PotatoLLMError("offline")):
            self.assertEqual(p.suggest_smaller("llama3:70b", "do not try"), "try a 3B or smaller quantized model")


def fake_sampler(min_ram_free=None, max_pagefile_used=None):
    return SimpleNamespace(min_ram_free=min_ram_free, max_pagefile_used=max_pagefile_used)


class PagingTests(unittest.TestCase):
    def test_detect_paging(self):
        before = {"pagefile_used_gb": 1.0}
        self.assertFalse(p.detect_paging(before, fake_sampler(2.0, 1.1), {}))
        self.assertTrue(p.detect_paging(before, fake_sampler(2.0, 1.3), {}))
        self.assertTrue(p.detect_paging(before, fake_sampler(0.1, 1.0), {}))
        self.assertEqual(p.detect_paging({"pagefile_used_gb": p.UNKNOWN}, fake_sampler(2.0, 1.0), {}), p.UNKNOWN)
        self.assertEqual(p.detect_paging(before, fake_sampler(2.0, None), {}), p.UNKNOWN)

    def test_sampler_tracks_min_free_and_peak_pagefile(self):
        snapshots = iter([
            {"ram_free_gb": 3.0, "pagefile_used_gb": 1.0},
            {"ram_free_gb": 0.1, "pagefile_used_gb": 2.5},
            {"ram_free_gb": 2.0, "pagefile_used_gb": 1.5},
        ])
        sampler = p.Sampler()
        with mock.patch.object(p, "get_memory_snapshot", side_effect=lambda: next(snapshots)):
            sampler._sample()
            sampler._sample()
            self.assertIsNotNone(sampler.low_ram_since)
            sampler._sample()
        self.assertEqual(sampler.min_ram_free, 0.1)
        self.assertEqual(sampler.max_pagefile_used, 2.5)
        # RAM came back, so the thrashing clock resets.
        self.assertIsNone(sampler.low_ram_since)
        self.assertEqual(sampler.thrashing_for(), 0.0)


class ResultTests(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(p, "get_ollama_version", return_value="0.0.0"),
            mock.patch.object(p, "get_cpu_name", return_value="test-cpu"),
            mock.patch.object(p, "get_os_name", return_value="test-os"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_build_result_uses_ollama_eval_timing(self):
        before = {"ram_total_gb": 8.0, "pagefile_used_gb": 1.0}
        response = {"eval_count": 100, "eval_duration": 4_000_000_000}
        result = p.build_result("m:1b", {"size_gb": 1.0, "quantization": "Q4_0"}, before, fake_sampler(3.0, 1.0), {}, response, 9.9)
        self.assertEqual(result["tok_s"], 25.0)
        self.assertEqual(result["duration_s"], 4.0)
        self.assertEqual(result["generated_tokens"], 100)
        self.assertFalse(result["paged"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["schema_version"], p.SCHEMA_VERSION)

    def test_build_result_without_eval_fields(self):
        before = {"ram_total_gb": 8.0, "pagefile_used_gb": 1.0}
        result = p.build_result("m", {}, before, fake_sampler(None, None), {}, {}, 2.5)
        self.assertEqual(result["tok_s"], p.UNKNOWN)
        self.assertEqual(result["duration_s"], 2.5)
        self.assertEqual(result["generated_tokens"], p.UNKNOWN)
        self.assertEqual(result["min_free_ram_gb"], p.UNKNOWN)
        self.assertEqual(result["paged"], p.UNKNOWN)

    def test_aborted_result_is_marked_paged(self):
        result = p.build_aborted_result("m", {}, {"ram_total_gb": 8.0}, fake_sampler(0.05, 3.0), {}, 21.0)
        self.assertTrue(result["paged"])
        self.assertTrue(result["status"].startswith("aborted"))
        self.assertEqual(result["duration_s"], 21.0)

    def test_normalize_result_upgrades_schema_1(self):
        old = {
            "schema_version": "1.0", "data": "2026-08-20", "modelo": "qwen3:4b",
            "quantizacao": "Q4_K_M", "tamanho": 2.5, "tok_s": 3.2, "paginou": True,
        }
        new = p.normalize_result(old)
        self.assertEqual(new["schema_version"], p.SCHEMA_VERSION)
        self.assertEqual(new["model"], "qwen3:4b")
        self.assertEqual(new["date"], "2026-08-20")
        self.assertEqual(new["size_gb"], 2.5)
        self.assertTrue(new["paged"])
        self.assertEqual(new["cpu"], p.UNKNOWN)
        self.assertEqual(new["status"], "completed")

    def test_normalize_result_rejects_unknown_schema(self):
        self.assertIsNone(p.normalize_result({"schema_version": "9.9"}))
        self.assertIsNone(p.normalize_result(["not", "a", "dict"]))
        current = {"schema_version": p.SCHEMA_VERSION, "model": "x"}
        self.assertIs(p.normalize_result(current), current)

    def test_format_table_hides_selftest_and_renders_booleans(self):
        rows = [
            {"date": "2026-08-20T17:51:47-03:00", "model": "qwen3:4b", "paged": True, "size_gb": 2.5},
            {"model": "selftest-example"},
            {"date": "2026-08-20", "model": "q:1b", "paged": None},
        ]
        table = p.format_table(rows)
        lines = table.splitlines()
        self.assertEqual(len(lines), 4)  # header, separator, two rows
        self.assertNotIn("selftest-example", table)
        self.assertIn("| 2026-08-20 | qwen3:4b |", lines[2])
        self.assertTrue(lines[2].endswith("| yes |"))
        self.assertTrue(lines[3].endswith("| unknown |"))

    def test_write_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            result = {"schema_version": p.SCHEMA_VERSION, "model": "m", "z": 1, "a": 2}
            written = p.write_result(result, path=path)
            self.assertEqual(written, path)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertLess(text.index('"a"'), text.index('"z"'))  # sorted keys
            self.assertEqual(p.load_result_file(path), result)

    def test_load_result_file_skips_bad_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            old_schema = Path(tmp) / "old.json"
            old_schema.write_text(json.dumps({"schema_version": "0.1"}), encoding="utf-8")
            with mock.patch("sys.stderr"):
                self.assertIsNone(p.load_result_file(broken))
                self.assertIsNone(p.load_result_file(old_schema))
                self.assertIsNone(p.load_result_file(Path(tmp) / "missing.json"))

    def test_committed_results_render_in_table(self):
        paths = sorted(p.RESULTS_DIR.glob("*.json"))
        self.assertTrue(paths, "results/ should ship at least one measurement")
        results = [p.load_result_file(path) for path in paths]
        self.assertTrue(all(results))
        self.assertIn("qwen", p.format_table(results))


if __name__ == "__main__":
    unittest.main()
