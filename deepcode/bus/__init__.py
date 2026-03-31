"""Message bus for decoupled channel-agent communication."""

from deepcode.bus.events import InboundMessage, OutboundMessage
from deepcode.bus.queue import MessageBus

__all__ = ["InboundMessage", "OutboundMessage", "MessageBus"]
