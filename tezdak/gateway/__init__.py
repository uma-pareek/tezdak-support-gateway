"""Channel gateway in front of the support agent (WhatsApp, in-app chat).

The gateway never imports the agent; `Gateway` takes an `agent_handle` callable.
"""

from .config import GatewayConfig
from .message import InboundMessage, OutboundMessage
from .router import Gateway

__all__ = ["Gateway", "GatewayConfig", "InboundMessage", "OutboundMessage"]
