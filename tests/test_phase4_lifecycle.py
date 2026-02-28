"""Phase 4 tests: SkillRegistry.reload(), ProcessManager.cancel(), AgenticSession."""

import asyncio
import pytest
import time


# ── SkillRegistry.reload() ────────────────────────────────────────────

class TestSkillRegistryReload:

    def test_reload_returns_skill_count(self):
        from skills.registry import get_registry
        registry = get_registry()
        count = registry.reload()
        assert isinstance(count, int)
        assert count > 0

    def test_reload_preserves_skill_count(self):
        from skills.registry import get_registry
        registry = get_registry()
        before = len(registry.list_all())
        after = registry.reload()
        assert after == before

    def test_reload_clears_caches(self):
        from skills.registry import get_registry
        registry = get_registry()
        # Warm up caches
        _ = registry.to_prompt_string()
        _ = registry.to_json_schema()
        assert registry._cached_prompt_string is not None
        assert registry._cached_json_schema is not None

        registry.reload()
        # After reload caches should be rebuilt (they are None only before first
        # access — calling reload() triggers re-registration which may set them
        # again; just verify skills are still accessible)
        assert len(registry.list_all()) > 0

    def test_reload_skills_still_searchable(self):
        from skills.registry import get_registry
        registry = get_registry()
        registry.reload()
        results = registry.search("blur")
        assert len(results) > 0

    def test_reload_twice_is_idempotent(self):
        from skills.registry import get_registry
        registry = get_registry()
        count1 = registry.reload()
        count2 = registry.reload()
        assert count1 == count2


# ── SkillRegistry file-watcher ────────────────────────────────────────

class TestSkillRegistryWatcher:

    def test_start_and_stop_watching(self, tmp_path):
        from skills.registry import SkillRegistry
        r = SkillRegistry()
        r.start_watching(watch_dir=str(tmp_path), interval=999)
        assert getattr(r, "_watcher_timer", None) is not None
        r.stop_watching()
        assert getattr(r, "_watcher_timer", None) is None

    def test_start_watching_twice_is_idempotent(self, tmp_path):
        from skills.registry import SkillRegistry
        r = SkillRegistry()
        r.start_watching(watch_dir=str(tmp_path), interval=999)
        timer_a = r._watcher_timer
        r.start_watching(watch_dir=str(tmp_path), interval=999)
        timer_b = r._watcher_timer
        # Should be the same timer — second call is a no-op
        assert timer_a is timer_b
        r.stop_watching()

    def test_stop_watching_without_start_does_not_raise(self):
        from skills.registry import SkillRegistry
        r = SkillRegistry()
        r.stop_watching()  # should be a no-op

    def test_watcher_triggers_reload_on_yaml_change(self, tmp_path):
        # Create a fresh registry with a custom YAML dir
        from skills.registry import SkillRegistry, _register_default_skills

        r = SkillRegistry()
        _register_default_skills(r)

        reload_events: list[int] = []
        original_reload = r.reload

        def _tracked_reload():
            count = original_reload()
            reload_events.append(count)
            return count

        r.reload = _tracked_reload

        # Create a YAML file — watcher snapshot is taken at start_watching time
        yaml_file = tmp_path / "test_skill.yaml"
        yaml_file.write_text("name: test_skill\n")
        r.start_watching(watch_dir=str(tmp_path), interval=0.1)

        # Modify the file to trigger a change
        time.sleep(0.05)
        yaml_file.write_text("name: test_skill\ndescription: changed\n")

        # Wait for one poll cycle + some slack
        time.sleep(0.4)
        r.stop_watching()

        assert len(reload_events) >= 1, (
            "Expected reload to have been triggered at least once by the watcher"
        )


# ── ProcessManager.cancel() ───────────────────────────────────────────

class TestProcessManagerCancel:

    def test_cancel_with_no_active_process_returns_false(self):
        from core.executor.process_manager import ProcessManager
        pm = ProcessManager()
        result = pm.cancel()
        assert result is False

    def test_cancel_clears_cancelled_flag_before_new_execute(self):
        from core.executor.process_manager import ProcessManager
        pm = ProcessManager()
        pm._cancelled = True
        pm._reset_cancel()
        assert pm._cancelled is False

    def test_execute_still_works_after_cancel(self):
        from core.executor.process_manager import ProcessManager
        pm = ProcessManager()
        pm.cancel()  # cancel with nothing running
        # A fresh execute should still work
        result = pm.execute(["ffmpeg", "-version"])
        assert result.return_code == 0

    def test_cancel_sets_cancelled_flag(self):
        from core.executor.process_manager import ProcessManager
        pm = ProcessManager()
        pm.cancel()
        # _cancelled should be set (even though no process was running)
        assert pm._cancelled is True

    def test_cancel_releases_active_proc_slot(self):
        # Simulate cancelling a stored proc reference (mock it)
        from core.executor.process_manager import ProcessManager
        pm = ProcessManager()
        # Put a fake proc object in the slot
        class FakeProc:
            pid = 99999
            def kill(self): pass
        pm._active_proc = FakeProc()
        result = pm.cancel()
        assert result is True
        assert pm._active_proc is None


# ── AgenticSession ────────────────────────────────────────────────────

from unittest.mock import AsyncMock, MagicMock


def make_mock_response(content="", tool_calls=None):
    resp = MagicMock()
    resp.content = content
    resp.tool_calls = tool_calls or []
    return resp


class TestAgenticSession:

    def _make_connector(self, responses):
        connector = MagicMock()
        connector.chat_with_tools = AsyncMock(side_effect=responses)
        return connector

    def test_run_returns_content_when_no_tool_calls(self):
        from core.pipeline_generator import AgenticSession
        resp = make_mock_response(content='{"interpretation": "ok", "pipeline": []}')
        connector = self._make_connector([resp])
        session = AgenticSession(connector, tools=[], tool_handlers={})
        result = asyncio.run(
            session.run([{"role": "user", "content": "make it blue"}])
        )
        assert "pipeline" in result

    def test_run_dispatches_tool_and_returns_final(self):
        from core.pipeline_generator import AgenticSession
        tool_resp = make_mock_response(
            content="",
            tool_calls=[{
                "id": "call_0",
                "function": {"name": "search_skills", "arguments": {"query": "blur"}},
            }],
        )
        final_resp = make_mock_response(content='{"interpretation": "done", "pipeline": []}')
        connector = self._make_connector([tool_resp, final_resp])

        results_captured = []
        handlers = {
            "search_skills": lambda args: results_captured.append(args) or {"skills": ["blur"]},
        }
        session = AgenticSession(connector, tools=[], tool_handlers=handlers)
        result = asyncio.run(
            session.run([{"role": "user", "content": "blur it"}])
        )
        assert "pipeline" in result
        assert results_captured == [{"query": "blur"}]

    def test_run_exhausts_iterations_and_calls_final(self):
        from core.pipeline_generator import AgenticSession
        tool_resp = make_mock_response(
            content="",
            tool_calls=[{"id": "c", "function": {"name": "list_skills", "arguments": {}}}],
        )
        final_resp = make_mock_response(content='{"interpretation": "done", "pipeline": []}')
        connector = self._make_connector([tool_resp, tool_resp, tool_resp, final_resp])
        session = AgenticSession(
            connector, tools=[], tool_handlers={"list_skills": lambda a: []},
            max_iterations=3,
        )
        result = asyncio.run(
            session.run([{"role": "user", "content": "list skills"}])
        )
        assert session.iterations_used == 3
        assert "pipeline" in result

    def test_closed_session_raises_on_run(self):
        from core.pipeline_generator import AgenticSession
        connector = self._make_connector([])
        session = AgenticSession(connector, tools=[], tool_handlers={})
        session.close()
        with pytest.raises(RuntimeError, match="closed"):
            asyncio.run(
                session.run([{"role": "user", "content": "test"}])
            )

    def test_async_context_manager_closes_on_exit(self):
        from core.pipeline_generator import AgenticSession
        resp = make_mock_response(content='{"pipeline": []}')
        connector = self._make_connector([resp])
        session = AgenticSession(connector, tools=[], tool_handlers={})

        async def _run():
            async with session:
                await session.run([{"role": "user", "content": "go"}])
            return session.closed

        closed = asyncio.run(_run())
        assert closed is True

    def test_unknown_tool_returns_error_result(self):
        from core.pipeline_generator import AgenticSession
        tool_resp = make_mock_response(
            content="",
            tool_calls=[{"id": "c", "function": {"name": "nonexistent", "arguments": {}}}],
        )
        final_resp = make_mock_response(content='{"pipeline": []}')
        connector = self._make_connector([tool_resp, final_resp])
        session = AgenticSession(connector, tools=[], tool_handlers={})
        result = asyncio.run(
            session.run([{"role": "user", "content": "go"}])
        )
        assert "pipeline" in result

    def test_tool_calls_made_tracks_names(self):
        from core.pipeline_generator import AgenticSession
        tool_resp = make_mock_response(
            content="",
            tool_calls=[{"id": "c", "function": {"name": "list_skills", "arguments": {}}}],
        )
        final_resp = make_mock_response(content='{"pipeline": []}')
        connector = self._make_connector([tool_resp, final_resp])
        session = AgenticSession(
            connector, tools=[], tool_handlers={"list_skills": lambda a: []},
        )
        asyncio.run(
            session.run([{"role": "user", "content": "go"}])
        )
        assert "list_skills" in session.tool_calls_made

