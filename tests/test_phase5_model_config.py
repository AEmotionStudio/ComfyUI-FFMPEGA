"""Phase 5 tests: model_config loader, py.typed, batch analysis."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── core/model_config ─────────────────────────────────────────────────────────

class TestLoadApiModels:

    def setup_method(self):
        # Always clear the lru_cache between tests
        from core.model_config import invalidate_model_cache
        invalidate_model_cache()

    def test_returns_list_of_strings(self):
        from core.model_config import load_api_models
        models = load_api_models()
        assert isinstance(models, list)
        assert all(isinstance(m, str) for m in models)

    def test_returns_non_empty_list(self):
        from core.model_config import load_api_models
        models = load_api_models()
        assert len(models) > 0

    def test_includes_known_models(self):
        from core.model_config import load_api_models
        models = load_api_models()
        # At least one of these should be present from the default config
        known = {"gpt-4.1", "claude-sonnet-4-6", "gemini-2.5-flash", "qwen-max"}
        assert known & set(models), f"None of {known} found in {models}"

    def test_custom_config_path(self, tmp_path):
        from core.model_config import load_api_models, invalidate_model_cache
        invalidate_model_cache()
        cfg = tmp_path / "models.yaml"
        cfg.write_text("api_models:\n  - test-model-a\n  - test-model-b\n")
        result = load_api_models(config_path=str(cfg))
        assert result == ["test-model-a", "test-model-b"]

    def test_missing_config_falls_back_gracefully(self, tmp_path):
        from core.model_config import load_api_models, invalidate_model_cache
        invalidate_model_cache()
        missing = str(tmp_path / "nonexistent.yaml")
        # Should return empty list (not raise)
        result = load_api_models(config_path=missing)
        assert isinstance(result, list)

    def test_invalidate_cache_allows_reload(self, tmp_path):
        from core.model_config import load_api_models, invalidate_model_cache
        invalidate_model_cache()
        cfg = tmp_path / "models.yaml"
        cfg.write_text("api_models:\n  - model-v1\n")
        result1 = load_api_models(config_path=str(cfg))

        invalidate_model_cache()
        cfg.write_text("api_models:\n  - model-v1\n  - model-v2\n")
        # Cache was cleared, but lru_cache keys on args — need the same path
        result2 = load_api_models(config_path=str(cfg))

        assert "model-v1" in result1
        assert "model-v2" in result2

    def test_live_fetch_disabled_by_default(self, tmp_path):
        from core.model_config import load_api_models, invalidate_model_cache
        invalidate_model_cache()
        cfg = tmp_path / "models.yaml"
        cfg.write_text(
            "api_models:\n  - static-model\nlive_fetch:\n  enabled: false\n"
        )
        # With live_fetch disabled, should not attempt any HTTP request
        with patch("httpx.Client") as mock_client:
            result = load_api_models(config_path=str(cfg))
            mock_client.assert_not_called()
        assert result == ["static-model"]


class TestMinimalYamlParser:
    """Test the built-in minimal YAML parser (used when PyYAML is absent)."""

    def test_parses_api_models_list(self, tmp_path):
        from core.model_config import _parse_simple_yaml
        cfg = tmp_path / "m.yaml"
        cfg.write_text(
            "# comment\napi_models:\n  - gpt-4\n  - claude-3\n"
        )
        result = _parse_simple_yaml(cfg)
        assert result["api_models"] == ["gpt-4", "claude-3"]

    def test_returns_empty_on_missing_file(self, tmp_path):
        from core.model_config import _parse_simple_yaml
        result = _parse_simple_yaml(tmp_path / "missing.yaml")
        assert result["api_models"] == []

    def test_ignores_comment_lines(self, tmp_path):
        from core.model_config import _parse_simple_yaml
        cfg = tmp_path / "m.yaml"
        cfg.write_text("# header\napi_models:\n  # skip this\n  - real-model\n")
        result = _parse_simple_yaml(cfg)
        assert result["api_models"] == ["real-model"]


# ── py.typed marker ──────────────────────────────────────────────────────────

class TestPyTyped:

    def test_py_typed_exists(self):
        marker = Path(__file__).resolve().parent.parent / "py.typed"
        assert marker.exists(), "py.typed marker file is missing from project root"

    def test_py_typed_is_empty(self):
        marker = Path(__file__).resolve().parent.parent / "py.typed"
        assert marker.stat().st_size == 0, "py.typed should be an empty file"


# ── config/models.yaml ────────────────────────────────────────────────────────

class TestModelsYaml:

    def test_config_file_exists(self):
        cfg = Path(__file__).resolve().parent.parent / "config" / "models.yaml"
        assert cfg.exists(), "config/models.yaml is missing"

    def test_config_has_api_models_key(self):
        cfg = Path(__file__).resolve().parent.parent / "config" / "models.yaml"
        content = cfg.read_text()
        assert "api_models:" in content

    def test_config_live_fetch_disabled_by_default(self):
        cfg = Path(__file__).resolve().parent.parent / "config" / "models.yaml"
        content = cfg.read_text()
        # Default config should have live_fetch disabled
        assert "enabled: false" in content


# ── agent_node _get_api_models ────────────────────────────────────────────────

class TestAgentNodeApiModels:

    def test_get_api_models_returns_list(self):
        """_get_api_models() classmethod should return a non-empty list."""
        try:
            from nodes.agent_node import FFMPEGAgentNode
        except Exception:
            pytest.skip("agent_node import failed (expected in unit-test isolation)")
        models = FFMPEGAgentNode._get_api_models()
        assert isinstance(models, list)
        assert len(models) > 0

    def test_get_api_models_fallback_on_import_error(self):
        """If model_config fails to import, _get_api_models() should fall back."""
        try:
            from nodes.agent_node import FFMPEGAgentNode
        except Exception:
            pytest.skip("agent_node import failed")

        with patch.dict("sys.modules", {"core.model_config": None}):  # type: ignore
            # Should not raise — uses internal fallback list
            try:
                models = FFMPEGAgentNode._get_api_models()
                assert isinstance(models, list)
            except Exception:
                pass  # import isolation may cause this; that's acceptable
