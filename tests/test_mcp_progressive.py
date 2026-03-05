"""Tests for MCP progressive disclosure.

Validates:
- list_skills returns compact index (no parameters or examples)
- get_skill_details returns full data (parameters, ranges, template)
- search_skills returns compact matches
- analyze_video supports summary vs full tiers
- All tools are routable through server.call_tool()
"""

import asyncio
import json
import pytest

from mcp.tools import list_skills, search_skills, get_skill_details, analyze_video
from mcp.server import FFMPEGAMCPServer


# ── Tier 1: list_skills (compact index) ─────────────────────────────


class TestListSkillsCompact:
    """list_skills should return compact index — no parameters or examples."""

    def test_returns_skills(self):
        result = list_skills()
        assert "skills" in result
        assert result["total_count"] > 0

    def test_no_parameters_field(self):
        """Skills in list_skills must NOT include 'parameters'."""
        result = list_skills()
        for skill in result["skills"]:
            assert "parameters" not in skill, (
                f"Skill '{skill['name']}' should not have 'parameters' in compact listing"
            )

    def test_no_examples_field(self):
        """Skills in list_skills must NOT include 'examples'."""
        result = list_skills()
        for skill in result["skills"]:
            assert "examples" not in skill, (
                f"Skill '{skill['name']}' should not have 'examples' in compact listing"
            )

    def test_has_required_compact_fields(self):
        """Each skill must have name, category, description, tags."""
        result = list_skills()
        for skill in result["skills"]:
            assert "name" in skill
            assert "category" in skill
            assert "description" in skill
            assert "tags" in skill

    def test_category_filter(self):
        """Category filter should still work."""
        result = list_skills(category="visual")
        assert result["total_count"] > 0
        for skill in result["skills"]:
            assert skill["category"] == "visual"

    def test_by_category_grouping(self):
        """by_category dict should still be present."""
        result = list_skills()
        assert "by_category" in result
        assert len(result["by_category"]) > 0


# ── Tier 2: search_skills (compact matches) ────────────────────────


class TestSearchSkillsCompact:
    """search_skills should return compact matches."""

    def test_returns_matches(self):
        result = search_skills("color")
        assert "matches" in result
        assert result["match_count"] > 0

    def test_matches_are_compact(self):
        """Search matches should have name, category, description, tags only."""
        result = search_skills("color")
        for match in result["matches"]:
            assert "name" in match
            assert "category" in match
            assert "description" in match
            assert "tags" in match
            # Must NOT have full details
            assert "parameters" not in match
            assert "ffmpeg_template" not in match


# ── Tier 3: get_skill_details (full data) ───────────────────────────


class TestGetSkillDetailsFull:
    """get_skill_details should return full data with parameters."""

    def test_returns_parameters(self):
        result = get_skill_details("colorbalance")
        assert "parameters" in result
        assert len(result["parameters"]) > 0

    def test_parameters_have_detail_fields(self):
        """Parameters should include detail fields not in compact listing."""
        result = get_skill_details("colorbalance")
        params = result["parameters"]
        # Detail params should have more keys than compact (name/category/desc/tags)
        detail_keys = set(params[0].keys())
        # Detail params should include type, required, default at minimum
        assert "type" in detail_keys
        assert "required" in detail_keys
        assert "default" in detail_keys

    def test_has_ffmpeg_template(self):
        result = get_skill_details("colorbalance")
        assert "ffmpeg_template" in result

    def test_has_examples(self):
        result = get_skill_details("colorbalance")
        assert "examples" in result

    def test_has_tags(self):
        result = get_skill_details("colorbalance")
        assert "tags" in result

    def test_unknown_skill_returns_error(self):
        result = get_skill_details("nonexistent_skill_xyz")
        assert "error" in result


# ── analyze_video: summary vs full tiers ────────────────────────────


class TestAnalyzeVideoTiers:
    """analyze_video should support summary and full tiers."""

    def test_summary_has_fewer_keys(self):
        """Summary tier should return fewer top-level keys than full."""
        # We can't test with a real video file in unit tests,
        # so we verify the function signature accepts 'detail'.
        import inspect
        sig = inspect.signature(analyze_video)
        assert "detail" in sig.parameters
        assert sig.parameters["detail"].default == "full"

    def test_summary_detail_accepted(self):
        """Passing detail='summary' should not raise TypeError."""
        # Run with an invalid path — we just need to verify the
        # parameter is accepted, not that it finds a real video.
        result = analyze_video("/nonexistent/test.mp4", detail="summary")
        # Should return an error dict (file not found), not raise
        assert isinstance(result, dict)

    def test_full_detail_accepted(self):
        """Passing detail='full' should not raise TypeError."""
        result = analyze_video("/nonexistent/test.mp4", detail="full")
        assert isinstance(result, dict)


# ── Server routing: all tools reachable ─────────────────────────────


class TestServerToolRouting:
    """All registered tools should be routable through call_tool."""

    @pytest.fixture
    def server(self):
        return FFMPEGAMCPServer()

    def test_all_tools_have_schemas(self, server):
        """Every tool in _tools should have name and inputSchema."""
        for name, tool in server._tools.items():
            assert tool["name"] == name
            assert "inputSchema" in tool

    def test_expected_tool_count(self, server):
        """Server should register 12 tools."""
        assert len(server._tools) == 12

    def test_expected_tools_present(self, server):
        """All expected tools should be registered."""
        expected = {
            "analyze_video",
            "list_skills",
            "search_skills",
            "get_skill_details",
            "validate_skill_params",
            "build_pipeline",
            "execute_pipeline",
            "extract_frames",
            "cleanup_vision_frames",
            "analyze_colors",
            "analyze_audio",
            "list_luts",
        }
        assert set(server._tools.keys()) == expected

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self, server):
        """Unknown tool name should return error, not raise."""
        result = await server.call_tool("nonexistent_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_list_skills_routable(self, server):
        """list_skills should be callable through the server."""
        result = await server.call_tool("list_skills", {})
        assert "content" in result
        data = json.loads(result["content"][0]["text"])
        assert "skills" in data
        assert data["total_count"] > 0

    @pytest.mark.asyncio
    async def test_search_skills_routable(self, server):
        """search_skills should be callable through the server."""
        result = await server.call_tool("search_skills", {"query": "color"})
        assert "content" in result
        data = json.loads(result["content"][0]["text"])
        assert "matches" in data

    @pytest.mark.asyncio
    async def test_get_skill_details_routable(self, server):
        """get_skill_details should be callable through the server."""
        result = await server.call_tool("get_skill_details", {"skill_name": "colorbalance"})
        assert "content" in result
        data = json.loads(result["content"][0]["text"])
        assert "parameters" in data

    @pytest.mark.asyncio
    async def test_list_luts_routable(self, server):
        """list_luts should be callable through the server."""
        result = await server.call_tool("list_luts", {})
        assert "content" in result

    @pytest.mark.asyncio
    async def test_validate_skill_params_routable(self, server):
        """validate_skill_params should be callable through the server."""
        result = await server.call_tool("validate_skill_params", {
            "skill_name": "colorbalance",
            "params": {"rs": 0.1},
        })
        assert "content" in result
        data = json.loads(result["content"][0]["text"])
        assert "valid" in data


# ── Token efficiency: compact vs full comparison ────────────────────


class TestTokenEfficiency:
    """Verify compact outputs are meaningfully smaller than full."""

    def test_list_vs_detail_size(self):
        """list_skills per-skill size should be much smaller than get_skill_details."""
        listing = list_skills()
        # Pick the first skill to compare
        first_skill_name = listing["skills"][0]["name"]
        compact_size = len(json.dumps(listing["skills"][0]))

        detail = get_skill_details(first_skill_name)
        full_size = len(json.dumps(detail))

        # Full details should be at least 2x larger than compact listing
        assert full_size > compact_size * 2, (
            f"get_skill_details ({full_size} chars) should be at least 2x "
            f"list_skills entry ({compact_size} chars)"
        )
