"""
Interrupt manager for user-initiated agent cancellations.
In-memory registry checked during agent execution.
"""

import threading
from typing import Dict, Optional

from .logging import get_agent_logger

logger = get_agent_logger("interrupt_manager")

_interrupt_registry: Dict[str, threading.Event] = {}
_registry_lock = threading.Lock()


def register_conversation(conversation_id: str) -> None:
    with _registry_lock:
        if conversation_id not in _interrupt_registry:
            _interrupt_registry[conversation_id] = threading.Event()
            logger.debug(f"[INTERRUPT] Registered conversation: {conversation_id}")


def set_interrupt(conversation_id: str) -> None:
    with _registry_lock:
        if conversation_id not in _interrupt_registry:
            _interrupt_registry[conversation_id] = threading.Event()
        _interrupt_registry[conversation_id].set()
        logger.debug(f"[INTERRUPT] Interrupt set for conversation: {conversation_id}")


def clear_interrupt(conversation_id: str) -> None:
    with _registry_lock:
        if conversation_id in _interrupt_registry:
            _interrupt_registry[conversation_id].clear()
            logger.debug(f"[INTERRUPT] Interrupt cleared for conversation: {conversation_id}")


def is_interrupted(conversation_id: str) -> bool:
    with _registry_lock:
        if conversation_id in _interrupt_registry:
            return _interrupt_registry[conversation_id].is_set()
        return False


def cleanup_conversation(conversation_id: str) -> None:
    with _registry_lock:
        if conversation_id in _interrupt_registry:
            del _interrupt_registry[conversation_id]
            logger.debug(f"[INTERRUPT] Cleaned up conversation: {conversation_id}")


def get_interrupt_status(conversation_id: Optional[str] = None) -> dict:
    with _registry_lock:
        if conversation_id:
            return {
                "conversation_id": conversation_id,
                "interrupted": is_interrupted(conversation_id),
                "registered": conversation_id in _interrupt_registry,
            }
        return {
            "total_conversations": len(_interrupt_registry),
            "interrupted_conversations": [
                conv_id for conv_id, event in _interrupt_registry.items()
                if event.is_set()
            ],
        }
