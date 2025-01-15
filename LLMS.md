# LLMS.md — FFMPEGA AI Context

> This file provides context for AI coding agents working on this project.
> Following the [llms.txt](https://llmstxt.org) convention.

## Project Overview

**FFMPEGA** is a ComfyUI custom node that provides AI-powered video editing through natural language prompts. Users describe what they want ("make it cinematic", "slow motion with fade in") and an LLM agent translates the request into FFMPEG filter chains.

## Architecture

```
prompts/          → System prompts for LLM agent
  system.py       → Contains agentic and non-agentic system prompts
skills/           → The skill system (core concept)
  registry.py     → SkillRegistry, Skill, SkillParameter classes
  composer.py     → SkillComposer: maps skills → FFMPEG filter strings
  parser.py       → Parses "skill:param=value" notation
  category/       → Basic skills (temporal, spatial, visual, audio, encoding)
  outcome/        → Pre-built effect chains (cinematic, vintage, motion, etc.)
nodes/            → ComfyUI node definitions
  agent_node.py   → Main agentic node (LLM + tool calling loop)
  basic_node.py   → Simple prompt → ffmpeg node
mcp/              → Model Context Protocol server
  server.py       → MCP server with tools for external agents
  tools.py        → Tool implementations (search, analyze, build pipeline)
core/             → FFMPEG execution, video analysis, audio handling
```

## Key Concepts

### Skills
A **Skill** is a named video editing operation with typed parameters:
```python
Skill(name="brightness", category=SkillCategory.VISUAL,
      parameters=[SkillParameter(name="value", type=ParameterType.FLOAT)])
```

Skills are registered in `registry.py` and mapped to FFMPEG filters in `composer.py`.

### Pipeline
A pipeline is an ordered list of skill invocations:
```json
[{"skill": "speed", "params": {"factor": 0.5}},
 {"skill": "fade", "params": {"type": "in", "duration": 2}}]
```

### Composer
`SkillComposer._builtin_skill_filters()` maps each skill name to FFMPEG filter strings. This is where `speed` becomes `-filter:v "setpts=2.0*PTS"`.

## How to Add a New Skill

1. **Define the skill** in the appropriate file under `skills/category/` or `skills/outcome/`:
   ```python
   registry.register(Skill(
       name="my_skill",
       category=SkillCategory.VISUAL,
       description="What it does",
       parameters=[SkillParameter(name="amount", type=ParameterType.FLOAT, default=1.0)],
       examples=["my_skill:amount=2.0 - Double the effect"],
       tags=["effect", "visual"],
   ))
   ```

2. **Add the FFMPEG handler** in `skills/composer.py` → `_builtin_skill_filters()`:
   ```python
   elif skill_name == "my_skill":
       amount = params.get("amount", 1.0)
       video_filters.append(f"some_ffmpeg_filter={amount}")
   ```

3. **Register the module** (if new file) in `skills/registry.py` → `_register_default_skills()`.

## Common Patterns

- Skills return 3 lists: `video_filters`, `audio_filters`, `output_options`
- Use `params.get("name", default)` for all parameter access
- Parameters use Python types: `float()`, `int()`, `str()`
- FFMPEG expressions can use `t` (time), `iw`/`ih` (input width/height), `PI`, `random()`

## Dependencies
- Python 3.10+
- ffmpeg/ffprobe (system-installed)
- ollama (for LLM inference)
- ComfyUI (host application)
