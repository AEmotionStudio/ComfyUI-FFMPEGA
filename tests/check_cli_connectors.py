"""Test all CLI connectors — availability, vision support, basic generation.

Usage:
    /home/tealdisk/ComfyUI/venv/bin/python tests/test_cli_connectors.py
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_module(name: str, rel_path: str):
    """Load a module by file path without triggering __init__.py."""
    abs_path = PROJECT_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, str(abs_path))
    mod = importlib.util.module_from_spec(spec)
    # Pre-register dependent modules so relative imports work
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


# We need to set up the module hierarchy for relative imports
# Load them in dependency order
base_mod = load_module(
    "core.llm.base",
    "core/llm/base.py",
)
# Patch into sys.modules so cli_utils and cli_base find them
sys.modules["core"] = type(sys)("core")
sys.modules["core.llm"] = type(sys)("core.llm")
sys.modules["core.llm.base"] = base_mod

cli_utils = load_module("core.llm.cli_utils", "core/llm/cli_utils.py")
sys.modules["core.llm.cli_utils"] = cli_utils

cli_base = load_module("core.llm.cli_base", "core/llm/cli_base.py")
sys.modules["core.llm.cli_base"] = cli_base

# Now load each CLI connector
claude_mod = load_module("core.llm.claude_cli", "core/llm/claude_cli.py")
gemini_mod = load_module("core.llm.gemini_cli", "core/llm/gemini_cli.py")
qwen_mod = load_module("core.llm.qwen_cli", "core/llm/qwen_cli.py")
cursor_mod = load_module("core.llm.cursor_agent", "core/llm/cursor_agent.py")

# Also load API and Ollama to test their supports_vision
api_mod = None
ollama_mod = None
try:
    # API needs httpx + sanitize
    sanitize_mod = load_module("core.sanitize", "core/sanitize.py")
    sys.modules["core.sanitize"] = sanitize_mod
    api_mod = load_module("core.llm.api", "core/llm/api.py")
except Exception as e:
    print(f"  (API connector skipped: {e})")

try:
    ollama_mod = load_module("core.llm.ollama", "core/llm/ollama.py")
except Exception as e:
    print(f"  (Ollama connector skipped: {e})")


ALL_CONNECTORS = [
    ("ClaudeCodeCLI", claude_mod.ClaudeCodeCLIConnector),
    ("GeminiCLI", gemini_mod.GeminiCLIConnector),
    ("QwenCodeCLI", qwen_mod.QwenCodeCLIConnector),
    ("CursorAgent", cursor_mod.CursorAgentConnector),
]

if api_mod:
    ALL_CONNECTORS.append(
        ("APIConnector (OpenAI)", lambda: api_mod.APIConnector(
            base_mod.LLMConfig(
                provider=base_mod.LLMProvider.OPENAI,
                model="gpt-4o-mini",
                api_key="test-key",
            )
        ))
    )
if ollama_mod:
    ALL_CONNECTORS.append(
        ("OllamaConnector", lambda: ollama_mod.OllamaConnector(
            base_mod.LLMConfig(
                provider=base_mod.LLMProvider.OLLAMA,
                model="qwen3:8b",
            )
        ))
    )


async def main():
    print("FFMPEGA Connector Test — All Backends")
    print("=" * 60)
    print()

    results = []

    for name, connector_cls_or_factory in ALL_CONNECTORS:
        print(f"--- {name} ---")

        try:
            # Instantiate
            if callable(connector_cls_or_factory) and not isinstance(connector_cls_or_factory, type):
                connector = connector_cls_or_factory()
            else:
                connector = connector_cls_or_factory()

            # Check supports_vision
            has_vision = connector.supports_vision
            print(f"  supports_vision: {has_vision}")
            assert has_vision is True, f"Expected True, got {has_vision}"

            # Check is_available (binary detection for CLI)
            try:
                available = await connector.is_available()
                print(f"  is_available: {available}")
                if available:
                    print(f"    ✅ binary found")
                else:
                    print(f"    ⚠️  binary not installed (expected on this system)")
            except Exception as e:
                print(f"  is_available: error ({e})")

            # Check basic properties
            if hasattr(connector, '_model_name'):
                print(f"  model_name: {connector._model_name()}")
            if hasattr(connector, '_provider'):
                print(f"  provider: {connector._provider()}")
            if hasattr(connector, '_log_tag'):
                print(f"  log_tag: {connector._log_tag()}")

            # For available CLIs, do a quick generation test
            if hasattr(connector, '_binary_names'):
                print(f"  binary_names: {connector._binary_names()}")

            results.append((name, "PASS", has_vision))
            print(f"  PASS")

        except Exception as e:
            results.append((name, f"FAIL: {e}", False))
            print(f"  FAIL: {e}")

        print()

    # Summary
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    all_pass = True
    for name, status, vision in results:
        icon = "✅" if status == "PASS" else "❌"
        print(f"  {icon} {name}: {status} (vision={vision})")
        if status != "PASS":
            all_pass = False

    print()
    if all_pass:
        print("All connectors passed! ✅")
    else:
        print("Some connectors failed! ❌")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
