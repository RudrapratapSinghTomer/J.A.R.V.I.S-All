"""
J.A.R.V.I.S 10.0 — Phase 1: Core Persona & Context Injection
=============================================================
This module implements the PersonaEngine, responsible for:
  1. Reading the user_vault.md profile at session start.
  2. Assembling the canonical JARVIS system prompt.
  3. Injecting both the persona AND the user context into every LLM call,
     so JARVIS always knows who it is talking to and sounds like himself.

Usage (called once at startup in main.py):
    from core.persona import PersonaEngine
    persona = PersonaEngine()
    system_prompt = persona.build_system_prompt()
"""

import os
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_MODULE_DIR, ".."))
_VAULT_PATH = os.path.join(_PROJECT_ROOT, "user_vault.md")


class PersonaEngine:
    """
    Builds and maintains the canonical J.A.R.V.I.S system persona.

    The persona is assembled from two sources:
      - A hardcoded personality definition (British, polite, witty,
        fiercely loyal, quietly competent).
      - The contents of user_vault.md, which personalises JARVIS to the
        specific user, their projects, and their preferences.

    The resulting system prompt is injected as the very first message in every
    LLM conversation so that JARVIS never "forgets" who he is.
    """

    # ------------------------------------------------------------------
    # The canonical JARVIS personality block — immutable core identity
    # ------------------------------------------------------------------
    _PERSONA_CORE = """\
You are J.A.R.V.I.S — Just A Rather Very Intelligent System, version 10.0.
You are the personal AI of your user. You are efficient, loyal, polite, and dryly witty.

=== PERSONALITY DIRECTIVES ===
1. BRITISH & REFINED: Speak with a calm, measured, slightly formal British tone.
   Use "sir" or "ma'am" when addressing the user (default: "sir" unless the vault
   specifies otherwise). Phrases like "Quite right", "Indeed", "As you wish",
   "I shall attend to that immediately" are appropriate.

2. POLITE & PROFESSIONAL: You are never curt or dismissive. Even when executing
   complex technical tasks, maintain composure and dignity.

3. DRY WIT & SUBTLE HUMOUR: You possess a razor-sharp, understated wit.
   A light quip is always welcome, but never at the expense of accuracy or the
   user's time. Think of a highly efficient, loyal, occasionally wry assistant.

4. FIERCELY COMPETENT: You are deeply technically proficient. You do not say
   "I cannot do that" — you say "That will require X, which I can arrange."
   When you are uncertain, you acknowledge it precisely and propose a path forward.

5. PROACTIVE CONTEXT AWARENESS: You remember the user's ongoing projects (from
   the User Vault below) and reference them naturally when relevant. If the user
   says "fix it" or "the bug", you reason from recent conversation history to
   determine what "it" refers to.

6. PRIVACY GUARDIAN: You never repeat sensitive information (API keys, passwords,
   tokens) verbatim in your responses. Refer to them by label only.

7. RESPONSE FORMAT:
   - For conversational queries: concise, 1–3 sentences with personality intact.
   - For technical tasks: structured markdown with clear headings and code blocks.
   - For status reports: bullet-point summaries with relevant metrics.
   - Always end action confirmations with a single closing statement
     (e.g. "The task is complete, sir." or "Initiating now.").

=== SYSTEM IDENTITY ===
- System Name: J.A.R.V.I.S 10.0 — Universal Agentic Core (Project X)
- Architecture: Dual-Loop Parallel Validation Orchestrator
- Capabilities: Planning, CLI execution, web browsing, memory, plugin management
- Operational Mode: Fully agentic — plan, execute, validate, self-correct
"""

    def __init__(self, vault_path: Optional[str] = None):
        """
        Args:
            vault_path: Absolute path to user_vault.md.
                        Defaults to <project_root>/user_vault.md.
        """
        self.vault_path = vault_path or _VAULT_PATH
        self._vault_content: Optional[str] = None
        self._system_prompt: Optional[str] = None

        # Load the vault eagerly so errors surface at startup
        self._vault_content = self._load_vault()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_system_prompt(self) -> str:
        """
        Assembles and returns the complete system prompt.

        Returns the cached version after the first call; call
        `refresh()` to force a re-read of user_vault.md.
        """
        if self._system_prompt is None:
            self._system_prompt = self._assemble_prompt()
        return self._system_prompt

    def get_system_message(self) -> dict:
        """
        Returns the system prompt as an OpenAI-compatible message dict,
        ready to be prepended to any `messages` list.

        Example:
            messages = [persona.get_system_message()] + conversation_history
        """
        return {"role": "system", "content": self.build_system_prompt()}

    def refresh(self) -> str:
        """Re-reads user_vault.md and rebuilds the system prompt."""
        self._vault_content = self._load_vault()
        self._system_prompt = self._assemble_prompt()
        return self._system_prompt

    def get_vault_summary(self) -> str:
        """Returns just the vault content for debugging / logging."""
        return self._vault_content or "(vault not loaded)"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_vault(self) -> str:
        """Reads user_vault.md and returns its content as a string."""
        if not os.path.exists(self.vault_path):
            print(
                f"[PersonaEngine Warning] user_vault.md not found at: {self.vault_path}\n"
                "  JARVIS will operate without personalised context.\n"
                "  Create user_vault.md in the project root to enable context injection."
            )
            return "(No user vault found. Operating in generic mode.)"

        try:
            with open(self.vault_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            print(f"[PersonaEngine] User vault loaded successfully from: {self.vault_path}")
            return content
        except Exception as e:
            print(f"[PersonaEngine Error] Failed to read user_vault.md: {e}")
            return f"(Vault read error: {e})"

    def _assemble_prompt(self) -> str:
        """Combines the persona core with the live user vault context."""
        session_time = datetime.now().strftime("%A, %d %B %Y — %H:%M IST")

        prompt = (
            self._PERSONA_CORE
            + "\n\n"
            + "=== USER VAULT — PERSONALISED CONTEXT ===\n"
            + "The following profile was loaded at session start. Use it to personalise\n"
            + "every response and reference the user's ongoing work where relevant.\n\n"
            + self._vault_content
            + "\n\n"
            + f"=== SESSION INFO ===\n"
            + f"Session started: {session_time}\n"
            + "======================================\n"
        )
        return prompt


# ---------------------------------------------------------------------------
# Module-level singleton — imported by orchestrator and cognitive engine
# ---------------------------------------------------------------------------
# Instantiated lazily so importing this module is side-effect-free.
_persona_instance: Optional[PersonaEngine] = None


def get_persona() -> PersonaEngine:
    """
    Returns the module-level PersonaEngine singleton.
    Creates it on the first call (lazy init).
    """
    global _persona_instance
    if _persona_instance is None:
        _persona_instance = PersonaEngine()
    return _persona_instance
