# Contributing to ComfyUI-FFMPEGA

Thank you for considering contributing! This guide explains the project architecture, how to add features, and the code standards we follow.

## Architecture Overview

```
ComfyUI-FFMPEGA/
├── nodes/              # ComfyUI node definitions (entry points)
│   ├── agent_node.py   # Main FFMPEGAgentNode orchestrator
│   ├── input_resolver.py
│   ├── output_handler.py
│   ├── execution_engine.py
│   ├── batch_processor.py
│   └── nollm_modes.py
├── core/               # Business logic (no ComfyUI imports except platform.py)
│   ├── platform.py     # ComfyUI-specific adapters (folder_paths, VRAM)
│   ├── logging.py      # Structured logging (JSONFormatter, get_logger)
│   ├── pipeline_generator.py  # LLM-based pipeline generation
│   ├── llm/            # LLM connectors (Ollama, OpenAI, Anthropic, etc.)
│   ├── executor/       # FFmpeg process management
│   ├── sam3_masker.py   # SAM3 object masking
│   ├── whisper_transcriber.py
│   ├── mmaudio_synthesizer.py
│   ├── flux_klein_editor.py
│   └── ...
├── skills/             # Skill system (pure logic, no ComfyUI deps)
│   ├── registry.py     # Skill definitions and lookup
│   ├── composer.py     # Pipeline → FFmpeg command composition
│   ├── handlers/       # Skill-specific filter generation
│   ├── outcome/        # Pre-composed pipeline skills (cinematic, dreamy, etc.)
│   └── yaml_loader.py  # YAML skill loading
├── tests/              # ~850 tests (unit + integration)
│   ├── fixtures/       # Test video fixture
│   └── conftest.py     # Mocks for ComfyUI modules
└── stubs/              # Type stubs for ComfyUI-specific modules
```

**Key rule**: `core/` and `skills/` never import `folder_paths` or `comfy.*` directly. All ComfyUI-specific calls go through `core/platform.py`.

## How to Add a Skill

Skills are video/audio effects that compose into FFmpeg commands.

### 1. Define the skill

In the appropriate category file under `skills/` (e.g., `skills/outcome/effects.py`), or create a YAML definition:

```yaml
# skills/config/my_skill.yaml
name: my_effect
category: visual
description: Apply my custom effect
parameters:
  - name: intensity
    type: float
    description: Effect intensity
    default: 0.5
    min_value: 0.0
    max_value: 1.0
ffmpeg_template: "eq=brightness={intensity}"
```

### 2. Add a handler (if needed)

For complex skills that need custom logic beyond a simple template:

```python
# skills/handlers/visual.py
def handle_my_effect(params: dict, builder: CommandBuilder) -> None:
    intensity = params.get("intensity", 0.5)
    builder.vf(f"eq=brightness={intensity}")
```

Register the handler in `skills/handlers/__init__.py`.

### 3. Write a test

```python
# tests/test_skills.py
def test_my_effect():
    composer = SkillComposer()
    pipeline = Pipeline(input_path="/in.mp4", output_path="/out.mp4")
    pipeline.add_step("my_effect", {"intensity": 0.7})

    command = composer.compose(pipeline)
    assert "eq=brightness=0.7" in command.to_string()
```

### 4. Add an integration test (optional but encouraged)

```python
# tests/test_integration.py
def test_my_effect(self, test_video, output_path):
    composer = SkillComposer()
    pipeline = Pipeline(input_path=test_video, output_path=output_path)
    pipeline.add_step("my_effect", {"intensity": 0.5})
    pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

    result = _run_ffmpeg(composer.compose(pipeline))
    assert result.returncode == 0
```

## How to Add an LLM Connector

### 1. Subclass `LLMConnector`

```python
# core/llm/my_provider.py
from .base import LLMConnector, LLMConfig, LLMResponse

class MyProviderConnector(LLMConnector):
    """Connector for MyProvider API."""

    async def generate(self, prompt, system_prompt=None):
        messages = self.format_messages(prompt, system_prompt)
        # Call your API here
        return LLMResponse(
            content=response_text,
            model=self.config.model,
            provider=self.config.provider,
        )

    async def generate_stream(self, prompt, system_prompt=None):
        # Yield response chunks
        yield chunk

    async def list_models(self):
        return ["model-a", "model-b"]

    async def is_available(self):
        # Check API connectivity
        return True
```

### 2. Register in `pipeline_generator.py`

Add your provider to `PipelineGenerator.create_connector()`.

### 3. Write a test

Mock the API calls and test the connector logic in `tests/test_connectors_tools.py`.

## How to Run Tests

```bash
# Activate the ComfyUI venv
source venv/bin/activate

# Run all tests
python -m pytest tests/ -x -q

# Run with coverage
python -m pytest tests/ --cov=core --cov=skills --cov=nodes

# Run only integration tests (requires ffmpeg)
python -m pytest tests/test_integration.py -v

# Type check
python -m pyright
```

## Code Style

- **Formatter**: We use standard Python formatting (no specific formatter enforced yet)
- **Line length**: 120 characters
- **Type hints**: Required for all new functions. Use `from __future__ import annotations` for forward references
- **Logging**: Use `from core.logging import get_logger; log = get_logger(__name__)`
- **Docstrings**: Google-style docstrings with `Args:`, `Returns:`, `Raises:` sections
- **Imports**: Group as stdlib → third-party → local. Use `from .platform import ...` for ComfyUI adapters

## PR Guidelines

1. **One concern per PR** — don't mix features with refactors
2. **Tests required** — all new functionality needs tests
3. **Squash merge** — PRs are squashed on merge for clean history
4. **No direct ComfyUI imports in `core/`** — use `core/platform.py` adapters
5. **Run `python -m pytest tests/ -x -q`** before submitting
