"""
tests/test_persona.py — Phase 1 Unit Tests: Core Persona & Context Injection
=============================================================================
Run with:  python -m pytest tests/test_persona.py -v
"""

import os
import sys
import pytest
import tempfile

# Ensure J.A.R.V.I.S 10.0 core is importable
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from core.persona import PersonaEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_VAULT = """\
## Identity
- **Name:** Tony Stark
- **Preferred Address:** "sir"
- **Role:** Engineer

## Current Active Projects
- **Iron Man Suit v4** — Adding repulsor upgrades.

## Technical Preferences
- **Primary Language:** Python
"""


@pytest.fixture
def vault_file(tmp_path):
    """Creates a temporary user_vault.md for isolated testing."""
    vault = tmp_path / "user_vault.md"
    vault.write_text(SAMPLE_VAULT, encoding="utf-8")
    return str(vault)


@pytest.fixture
def missing_vault(tmp_path):
    """Returns a path to a vault that does NOT exist."""
    return str(tmp_path / "nonexistent_vault.md")


# ---------------------------------------------------------------------------
# Tests: PersonaEngine initialisation
# ---------------------------------------------------------------------------

class TestPersonaEngineInit:
    def test_loads_vault_successfully(self, vault_file):
        """PersonaEngine should read a valid vault file without errors."""
        engine = PersonaEngine(vault_path=vault_file)
        vault_content = engine.get_vault_summary()
        assert "Tony Stark" in vault_content
        assert "Iron Man Suit" in vault_content

    def test_missing_vault_returns_fallback(self, missing_vault):
        """PersonaEngine should gracefully degrade when vault is absent."""
        engine = PersonaEngine(vault_path=missing_vault)
        vault_content = engine.get_vault_summary()
        # Should NOT raise — should return a fallback string
        assert vault_content is not None
        assert "No user vault found" in vault_content or "generic mode" in vault_content


# ---------------------------------------------------------------------------
# Tests: System prompt assembly
# ---------------------------------------------------------------------------

class TestSystemPromptAssembly:
    def test_system_prompt_contains_persona_core(self, vault_file):
        """The assembled system prompt must contain J.A.R.V.I.S identity markers."""
        engine = PersonaEngine(vault_path=vault_file)
        prompt = engine.build_system_prompt()

        assert "J.A.R.V.I.S" in prompt
        assert "British" in prompt
        assert "sir" in prompt.lower()

    def test_system_prompt_contains_vault_content(self, vault_file):
        """The assembled system prompt must embed the user vault data."""
        engine = PersonaEngine(vault_path=vault_file)
        prompt = engine.build_system_prompt()

        assert "Tony Stark" in prompt
        assert "Iron Man Suit" in prompt

    def test_system_prompt_contains_session_info(self, vault_file):
        """The assembled system prompt should include a live session timestamp."""
        engine = PersonaEngine(vault_path=vault_file)
        prompt = engine.build_system_prompt()

        assert "Session started" in prompt

    def test_prompt_is_cached_on_second_call(self, vault_file):
        """build_system_prompt() should return the same object on repeated calls."""
        engine = PersonaEngine(vault_path=vault_file)
        prompt_1 = engine.build_system_prompt()
        prompt_2 = engine.build_system_prompt()
        assert prompt_1 is prompt_2  # Same object — cached

    def test_refresh_reloads_vault(self, tmp_path):
        """refresh() should pick up changes made to vault after init."""
        vault = tmp_path / "user_vault.md"
        vault.write_text("## Identity\n- **Name:** Bruce Banner\n", encoding="utf-8")

        engine = PersonaEngine(vault_path=str(vault))
        assert "Bruce Banner" in engine.build_system_prompt()

        # Update vault content
        vault.write_text("## Identity\n- **Name:** Thor Odinson\n", encoding="utf-8")
        refreshed = engine.refresh()

        assert "Thor Odinson" in refreshed
        assert "Bruce Banner" not in refreshed


# ---------------------------------------------------------------------------
# Tests: OpenAI-compatible message dict
# ---------------------------------------------------------------------------

class TestSystemMessage:
    def test_get_system_message_format(self, vault_file):
        """get_system_message() must return a valid OpenAI message dict."""
        engine = PersonaEngine(vault_path=vault_file)
        msg = engine.get_system_message()

        assert isinstance(msg, dict)
        assert msg.get("role") == "system"
        assert isinstance(msg.get("content"), str)
        assert len(msg["content"]) > 100  # Non-trivial content

    def test_system_message_contains_vault_and_persona(self, vault_file):
        """The system message content should unify both persona and vault."""
        engine = PersonaEngine(vault_path=vault_file)
        msg = engine.get_system_message()
        content = msg["content"]

        # Persona markers
        assert "J.A.R.V.I.S" in content
        # Vault markers
        assert "Tony Stark" in content


# ---------------------------------------------------------------------------
# Tests: Real vault on disk (integration smoke test)
# ---------------------------------------------------------------------------

class TestRealVaultIntegration:
    def test_real_vault_loads_if_present(self):
        """If the real user_vault.md exists in the project, it should load cleanly."""
        real_vault = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "user_vault.md")
        )
        if not os.path.exists(real_vault):
            pytest.skip("user_vault.md not present — skipping integration smoke test")

        engine = PersonaEngine(vault_path=real_vault)
        prompt = engine.build_system_prompt()

        # Core persona directives must always be present
        assert "J.A.R.V.I.S" in prompt
        assert "British" in prompt
        # Vault section header must be present
        assert "USER VAULT" in prompt
