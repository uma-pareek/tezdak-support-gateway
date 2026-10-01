"""Process entry: wires the chat gateway to the support agent.

    from tezdak.app import build_app
    app = build_app()
    out = app.gateway.on_message(raw_webhook_json, "whatsapp")

The carrier comes from the caller (a real client in production, the simulator in tests).
"""

from dataclasses import dataclass

from .agent import SupportAgent
from .backend.facade import Backend
from .carrier_client import CarrierClient
from .config import Config
from .gateway.router import Gateway
from .llm import LLMClient
from .metrics import Metrics


@dataclass
class App:
    gateway: Gateway
    agent: SupportAgent
    backend: Backend
    metrics: Metrics


def build_app(carrier=None, scenario=None, config=None, backend=None) -> App:
    """Build gateway + agent. `carrier` is a CarrierClient-like object; `scenario` seeds the simulator and stores."""
    if carrier is None:
        if scenario is None:
            raise ValueError("build_app needs a carrier or a scenario")
        carrier = CarrierClient.from_scenario(scenario)
    backend = backend or (Backend.from_scenario(scenario) if scenario else Backend.in_memory())
    metrics = Metrics()
    agent = SupportAgent(LLMClient(config or Config.from_env()), carrier, metrics=metrics, backend=backend)
    return App(gateway=Gateway(agent.handle), agent=agent, backend=backend, metrics=metrics)
