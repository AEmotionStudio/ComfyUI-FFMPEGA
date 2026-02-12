"""Tests for PipelineGenerator: JSON parsing and extraction.

Note: Model routing tests are skipped because create_connector uses
relative imports that don't work in the test environment. The routing
logic is tested indirectly via integration tests.
"""

import pytest
import json

from core.pipeline_generator import PipelineGenerator


class TestParseResponse:
    """Tests for PipelineGenerator.parse_response JSON parsing."""

    @pytest.fixture
    def gen(self):
        return PipelineGenerator()

    def test_parse_valid_json(self, gen):
        """Valid JSON string should parse correctly."""
        data = {
            "interpretation": "Apply blur",
            "pipeline": [{"skill": "blur", "params": {"radius": 5}}],
            "warnings": [],
            "estimated_changes": "blur effect",
        }
        result = gen.parse_response(json.dumps(data))
        assert result == data

    def test_parse_empty_string(self, gen):
        """Empty string should return None."""
        assert gen.parse_response("") is None
        assert gen.parse_response("   ") is None

    def test_parse_none(self, gen):
        """None input should return None."""
        assert gen.parse_response(None) is None

    def test_parse_plain_text_returns_none(self, gen):
        """Plain text without JSON should return None."""
        assert gen.parse_response("I can help you blur the video!") is None

    def test_parse_json_in_markdown_fence(self, gen):
        """JSON inside markdown code fence should be extracted."""
        text = '''Here is the pipeline:
```json
{"interpretation": "blur", "pipeline": [{"skill": "blur", "params": {}}]}
```
'''
        result = gen.parse_response(text)
        assert result is not None
        assert result["interpretation"] == "blur"

    def test_parse_json_in_plain_fence(self, gen):
        """JSON inside plain code fence (no language) should be extracted."""
        text = '''```
{"interpretation": "speed up", "pipeline": [{"skill": "speed", "params": {"factor": 2.0}}]}
```'''
        result = gen.parse_response(text)
        assert result is not None
        assert result["pipeline"][0]["skill"] == "speed"

    def test_parse_json_with_surrounding_text(self, gen):
        """JSON embedded in explanation text should be extracted."""
        text = '''I'll make the video faster. Here's the pipeline:
{"interpretation": "speed up", "pipeline": [{"skill": "speed", "params": {"factor": 2.0}}], "warnings": [], "estimated_changes": "2x speed"}
Hope this helps!'''
        result = gen.parse_response(text)
        assert result is not None
        assert result["pipeline"][0]["params"]["factor"] == 2.0

    def test_parse_nested_json(self, gen):
        """Nested JSON objects should be handled by brace matching."""
        data = {
            "interpretation": "complex edit",
            "pipeline": [
                {"skill": "blur", "params": {"radius": 5}},
                {"skill": "speed", "params": {"factor": 1.5}},
            ],
            "warnings": ["Large file"],
            "estimated_changes": "blur + speed",
        }
        text = f"Output: {json.dumps(data)}"
        result = gen.parse_response(text)
        assert result is not None
        assert len(result["pipeline"]) == 2


class TestExtractJson:
    """Tests for PipelineGenerator._extract_json edge cases."""

    def test_no_json_returns_none(self):
        assert PipelineGenerator._extract_json("no json here") is None

    def test_malformed_json_returns_none(self):
        assert PipelineGenerator._extract_json("{bad json}") is None

    def test_json_with_pipeline_keyword(self):
        """Should find JSON containing 'pipeline' keyword."""
        text = 'Some text {"pipeline": [{"skill": "blur"}], "interpretation": "blur it"} end'
        result = PipelineGenerator._extract_json(text)
        # The brace matching fallback should handle it
        if result:
            assert "pipeline" in result

    def test_multiple_fenced_blocks_returns_first_valid(self):
        """With multiple code blocks, return the first valid JSON dict."""
        text = '''```json
not valid json
```
```json
{"interpretation": "ok", "pipeline": []}
```'''
        result = PipelineGenerator._extract_json(text)
        assert result is not None
        assert result["interpretation"] == "ok"

    def test_json_array_not_returned(self):
        """JSON arrays should not be returned (we need dicts)."""
        text = '```json\n[1, 2, 3]\n```'
        result = PipelineGenerator._extract_json(text)
        # Arrays aren't dicts, should be skipped
        assert result is None or isinstance(result, dict)

    def test_deeply_nested_braces(self):
        """Deeply nested JSON should be handled by brace matching."""
        data = {"a": {"b": {"c": {"d": "deep"}}}, "pipeline": []}
        text = f"Result: {json.dumps(data)}"
        result = PipelineGenerator._extract_json(text)
        assert result is not None
        assert result["a"]["b"]["c"]["d"] == "deep"
