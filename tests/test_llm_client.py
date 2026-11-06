"""Model client: request shape, retries on busy replies, env and .env.prorated settings, reasoning replay switch."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from agent_fakes import FakeCarrier  # noqa: E402

from tezdak.agent import SupportAgent  # noqa: E402
from tezdak.config import Config, ConfigError, read_env_file  # noqa: E402
from tezdak.llm import LLMClient, LLMError, function_calls  # noqa: E402
from tezdak.policies import Policies  # noqa: E402


class _StubHandler(BaseHTTPRequestHandler):
    """Answers POSTs from a queue of (status, headers, body) set on the server."""

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.server.seen.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                 "body": json.loads(self.rfile.read(n) or b"{}")})
        status, headers, body = self.server.replies.pop(0) if self.server.replies else (200, {}, OK_REPLY)
        data = json.dumps(body).encode()
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


OK_REPLY = {"id": "resp_1", "output": [{"type": "message", "role": "assistant",
                                         "content": [{"type": "output_text", "text": "hi\nETA: none"}]}],
            "usage": {"input_tokens": 10, "output_tokens": 2}}


class StubServerCase(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
        self.server.replies, self.server.seen = [], []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d/v1" % self.server.server_address[1]
        self.llm = LLMClient(Config(llm_base_url=base, llm_token="k", llm_mode="live", llm_timeout_s=5))
        self.sleeps = []
        patcher = mock.patch("tezdak.llm.time.sleep", side_effect=self.sleeps.append)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()


class LiveClientTests(StubServerCase):
    def test_request_path_auth_and_body(self):
        self.llm.respond([{"role": "user", "content": "hi"}], tools=[{"type": "function", "name": "f"}])
        seen = self.server.seen[0]
        self.assertEqual(seen["path"], "/v1/responses")
        self.assertEqual(seen["auth"], "Bearer k")
        self.assertEqual(seen["body"]["reasoning"], {"effort": "low"})
        self.assertEqual(seen["body"]["max_output_tokens"], 1200)
        self.assertEqual(seen["body"]["tool_choice"], "auto")
        self.assertNotIn("model", seen["body"])

    def test_retries_busy_statuses_then_succeeds(self):
        self.server.replies = [(429, {"Retry-After": "7"}, {"error": {"code": "rate_limited"}}),
                               (503, {}, {"error": {"code": "too_many_in_flight"}}),
                               (502, {"Retry-After": "99"}, {"error": {"code": "llm_upstream_error"}})]
        resp = self.llm.respond([{"role": "user", "content": "hi"}])
        self.assertEqual(resp["id"], "resp_1")
        self.assertEqual(len(self.server.seen), 4)
        self.assertTrue(7 <= self.sleeps[0] <= 7.5, self.sleeps)
        self.assertTrue(3 <= self.sleeps[1] <= 3.5, self.sleeps)
        self.assertEqual(self.sleeps[2], 20)

    def test_gives_up_after_three_retries(self):
        self.server.replies = [(429, {"Retry-After": "0"}, {"error": {"code": "rate_limited"}})] * 4
        with self.assertRaises(LLMError) as ctx:
            self.llm.respond([{"role": "user", "content": "hi"}])
        self.assertIn("429", str(ctx.exception))
        self.assertIn("after 3 retries", str(ctx.exception))
        self.assertEqual(len(self.server.seen), 4)

    def test_other_errors_are_not_retried(self):
        self.server.replies = [(400, {}, {"error": {"code": "invalid_request"}})]
        with self.assertRaises(LLMError):
            self.llm.respond([{"role": "user", "content": "hi"}])
        self.assertEqual(len(self.server.seen), 1)
        self.assertEqual(self.sleeps, [])


class EnvConfigTests(unittest.TestCase):
    def test_mode_values(self):
        with self.assertRaises(ConfigError):
            Config.from_env({"LLM_MODE": "offline"})
        with self.assertRaises(ConfigError):
            Config.from_env({"LLM_MODE": "live", "OPENAI_BASE_URL": "http://x"})
        self.assertEqual(Config.from_env({"OPENAI_BASE_URL": "http://x"}).llm_mode, "mock")

    def test_replay_reasoning_flag(self):
        self.assertTrue(Config.from_env({}).llm_replay_reasoning)
        self.assertTrue(Config.from_env({"LLM_REPLAY_REASONING": "1"}).llm_replay_reasoning)
        self.assertFalse(Config.from_env({"LLM_REPLAY_REASONING": "0"}).llm_replay_reasoning)
        with self.assertRaises(ConfigError):
            Config.from_env({"LLM_REPLAY_REASONING": "maybe"})

    def test_env_file_parser(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, ".env.prorated")
            with open(path, "w") as fh:
                fh.write("# comment\n\nOPENAI_BASE_URL='http://a/v1'\nexport OPENAI_API_KEY=\"k1\"\nJUNK\nX=1=2\n")
            self.assertEqual(read_env_file(path), {"OPENAI_BASE_URL": "http://a/v1", "OPENAI_API_KEY": "k1", "X": "1=2"})
            self.assertEqual(read_env_file(os.path.join(d, "missing")), {})

    def test_env_file_loaded_from_working_directory(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, ".env.prorated"), "w") as fh:
                fh.write("OPENAI_BASE_URL=http://a/v1\nOPENAI_API_KEY=k1\nLLM_MODE=mock\n")
            os.chdir(d)
            try:
                clean = {k: v for k, v in os.environ.items() if not k.startswith(("OPENAI_", "LLM_"))}
                with mock.patch.dict(os.environ, clean, clear=True):
                    cfg = Config.from_env()
                    self.assertEqual((cfg.llm_base_url, cfg.llm_token, cfg.llm_mode), ("http://a/v1", "k1", "live"))
                with mock.patch.dict(os.environ, dict(clean, OPENAI_BASE_URL="http://b/v1", OPENAI_API_KEY="k2",
                                                      LLM_MODE="mock"), clear=True):
                    cfg = Config.from_env()
                    self.assertEqual((cfg.llm_base_url, cfg.llm_token, cfg.llm_mode), ("http://b/v1", "k2", "mock"))
            finally:
                os.chdir(cwd)


class ReplayReasoningTests(unittest.TestCase):
    def run_turn(self, replay):
        llm = LLMClient(Config(llm_mode="mock", llm_replay_reasoning=replay))
        planner_respond, inputs = llm._planner.respond, []

        def with_reasoning(messages, tools):
            inputs.append(list(messages))
            resp = planner_respond(messages, tools)
            if function_calls(resp):
                resp["output"].insert(0, {"type": "reasoning", "id": "rs_%d" % len(inputs), "summary": []})
            return resp

        llm._planner.respond = with_reasoning
        agent = SupportAgent(llm, FakeCarrier(), Policies())
        turn = agent.handle({"awb": "TZ4829301", "messages": [{"role": "user", "content": "Where is my parcel?"}]})
        return turn, inputs

    def test_reasoning_items_replayed_by_default(self):
        turn, inputs = self.run_turn(True)
        self.assertGreaterEqual(len(inputs), 2)
        self.assertTrue(any(m.get("type") == "reasoning" for m in inputs[-1]))
        self.assertNotEqual(turn.reply, "")

    def test_reasoning_items_dropped_when_switched_off(self):
        on, _ = self.run_turn(True)
        off, inputs = self.run_turn(False)
        self.assertGreaterEqual(len(inputs), 2)
        self.assertFalse(any(m.get("type") == "reasoning" for msgs in inputs for m in msgs))
        self.assertEqual(off.reply, on.reply)
        self.assertEqual([c["name"] for c in off.tool_calls], [c["name"] for c in on.tool_calls])


if __name__ == "__main__":
    unittest.main()
