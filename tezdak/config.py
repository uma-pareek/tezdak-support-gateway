"""Runtime configuration, read from environment variables only.

The model endpoint uses the usual OpenAI-style names, OPENAI_BASE_URL and OPENAI_API_KEY. If they are not set in
the environment, they are read from a `.env.prorated` file in the working directory when one exists.
"""

import os
from dataclasses import dataclass

LLM_PATH = "/responses"
MODES = ("mock", "live")
ENV_FILE = ".env.prorated"
FILE_KEYS = ("OPENAI_BASE_URL", "OPENAI_API_KEY")


class ConfigError(ValueError):
    pass


def read_env_file(path) -> dict:
    """Parse KEY=VALUE lines. Blank lines and # comments are skipped, surrounding quotes are dropped."""
    values = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _flag(value: str, name: str) -> bool:
    value = value.strip().lower()
    if value in ("", "1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ConfigError("%s must be 1 or 0, got %r" % (name, value))


@dataclass(frozen=True)
class Config:
    llm_base_url: str = ""
    llm_token: str = ""
    llm_mode: str = "mock"
    llm_timeout_s: float = 60.0
    max_model_calls: int = 6
    llm_replay_reasoning: bool = True

    @property
    def llm_url(self) -> str:
        return self.llm_base_url.rstrip("/") + LLM_PATH

    @classmethod
    def from_env(cls, environ=None, env_file=ENV_FILE) -> "Config":
        if environ is None:
            env = dict(os.environ)
            if env_file and not all(env.get(k, "").strip() for k in FILE_KEYS):
                for k, v in read_env_file(env_file).items():
                    if k in FILE_KEYS and not env.get(k, "").strip():
                        env[k] = v
        else:
            env = environ
        base = env.get("OPENAI_BASE_URL", "").strip()
        token = env.get("OPENAI_API_KEY", "").strip()
        mode = env.get("LLM_MODE", "").strip().lower()
        if mode and mode not in MODES:
            raise ConfigError("LLM_MODE must be one of %s, got %r" % (MODES, mode))
        if not mode:
            mode = "live" if (base and token) else "mock"
        if mode == "live" and not (base and token):
            raise ConfigError("live mode needs OPENAI_BASE_URL and OPENAI_API_KEY")
        replay = _flag(env.get("LLM_REPLAY_REASONING", ""), "LLM_REPLAY_REASONING")
        return cls(llm_base_url=base, llm_token=token, llm_mode=mode, llm_replay_reasoning=replay)
