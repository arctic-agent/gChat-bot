"""
Permanent Memory Module for Hermes Assistant.
Provides:
1. Persistent Thread Conversation Memory (stored in .thread_memory.json)
2. Persistent Fact & Knowledge Store (stored in .permanent_facts.json)
Survives process restarts, container rebuilds, and power cycles.
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("hermes-memory")
_lock = threading.Lock()

BASE_DIR = Path(__file__).resolve().parent
THREAD_MEMORY_FILE = BASE_DIR / ".thread_memory.json"
FACTS_MEMORY_FILE = BASE_DIR / ".permanent_facts.json"


def load_thread_memories() -> Dict[str, List[dict]]:
    """Loads saved thread conversation history from disk."""
    if not THREAD_MEMORY_FILE.exists():
        return {}
    try:
        with open(THREAD_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info("Loaded permanent memory for %d conversation threads.", len(data))
            return data
    except Exception:
        logger.exception("Failed to load thread memory file.")
        return {}


def save_thread_memories(memories: Dict[str, List[dict]]) -> None:
    """Atomically saves thread conversation history to disk."""
    with _lock:
        try:
            truncated = {}
            for tid, msgs in list(memories.items())[-100:]:
                truncated[tid] = msgs[-15:]

            temp_file = THREAD_MEMORY_FILE.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(truncated, f, indent=2, ensure_ascii=False)
            temp_file.replace(THREAD_MEMORY_FILE)
        except Exception:
            logger.exception("Failed to persist thread memory.")


def load_permanent_facts() -> Dict[str, str]:
    """Loads permanent knowledge facts from disk."""
    if not FACTS_MEMORY_FILE.exists():
        return {}
    try:
        with open(FACTS_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load permanent facts file.")
        return {}


def save_fact(key: str, value: str) -> bool:
    """Saves a permanent fact or key learning to disk."""
    with _lock:
        try:
            facts = load_permanent_facts()
            facts[key.strip()] = value.strip()
            temp_file = FACTS_MEMORY_FILE.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(facts, f, indent=2, ensure_ascii=False)
            temp_file.replace(FACTS_MEMORY_FILE)
            logger.info("Saved permanent memory fact [%s]: %r", key, value[:50])
            return True
        except Exception:
            logger.exception("Failed to save permanent fact.")
            return False


def get_permanent_facts_context() -> str:
    """Formats all permanent facts into a prompt context section."""
    facts = load_permanent_facts()
    if not facts:
        return ""
    lines = ["[PERMANENT MEMORY & ACCUMULATED KNOWLEDGE]:"]
    for k, v in facts.items():
        lines.append(f"• {k}: {v}")
    lines.append("[END OF PERMANENT MEMORY]\n")
    return "\n".join(lines)
