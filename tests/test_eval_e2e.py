import importlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import _eval_helpers as F


def available():
    try:
        importlib.import_module("carrier_sim")
        importlib.import_module("tezdak.agent")
        importlib.import_module("tezdak.llm")
    except ImportError:
        return False
    return True


@unittest.skipUnless(available(), "carrier_sim (PYTHONPATH=vendor:.) and tezdak are not both importable")
class RealEndToEnd(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("LLM_MODE")
        os.environ["LLM_MODE"] = "mock"

    def tearDown(self):
        if self._old is None:
            os.environ.pop("LLM_MODE", None)
        else:
            os.environ["LLM_MODE"] = self._old

    def test_cli_path_with_mock_llm(self):
        from eval.run_eval import run_dir
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "runs" / "e2e"
            rep = run_dir(F.DEV, out)
            self.assertEqual(len(rep["scenarios"]), 6)
            self.assertFalse(rep["errors"], rep["errors"])
            self.assertTrue((out / "report.md").exists())
            self.assertEqual(len(list((out / "traces").glob("*.jsonl"))), 6)
            on_disk = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk["scenarios"], rep["scenarios"])
            self.assertEqual(sorted(on_disk), ["diff_vs_previous", "errors", "llm", "name", "previous_run",
                                               "scenarios", "tezdak_hashes"])

    def test_llm_usage_is_summed_over_chats(self):
        from eval.run_eval import run_dir
        with tempfile.TemporaryDirectory() as d:
            rep = run_dir(F.DEV, Path(d) / "runs" / "sum")
        self.assertEqual(rep["llm"]["calls"], sum(c["llm"].get("calls", 0) for c in rep["scenarios"]))

    def test_cli_prints_one_line_per_chat_and_llm_usage(self):
        from eval.run_eval import main
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["--dir", str(F.DEV), "--out", str(Path(d) / "runs" / "cli")])
        self.assertEqual(code, 0)
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 6 + 2)
        self.assertTrue(lines[-2].startswith("LLM calls "), lines[-2])
        self.assertTrue(lines[-1].startswith("Report:"), lines[-1])


if __name__ == "__main__":
    unittest.main()
