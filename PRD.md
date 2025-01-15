# ComfyUI-FFMPEGA: Product Requirements Document (PRD)

## Executive Summary

ComfyUI-FFMPEGA is an intelligent FFMPEG agent node for ComfyUI that transforms natural language video editing prompts into precise, automated video transformations. Users connect a video source, describe their desired output in plain text, and the agent orchestrates the complete editing pipeline—from analysis to final render.

---

## 1. Vision & Goals

### 1.1 Vision Statement

Democratize professional video editing by enabling anyone to describe what they want in natural language and have an AI agent execute the technical FFMPEG operations automatically.

### 1.2 Primary Goals

- **Natural Language Editing**: Transform text prompts into FFMPEG command pipelines
- **Full Automation**: Agent analyzes input, plans operations, and executes multi-step workflows
- **ComfyUI Integration**: Seamless node-based workflow integration
- **Extensible Skills**: Modular skill system for expanding capabilities

### 1.3 Success Metrics

- Successfully parse and execute 90%+ of common video editing requests
- Support multi-step automated pipelines with 3+ chained operations
- Preview generation in <5 seconds for standard video lengths
- Batch processing of 10+ videos without manual intervention

---

## 2. User Stories & Use Cases

### 2.1 Primary User Stories

**US-1: Basic Video Transformation**
As a content creator, I want to type "make this video 720p, add a subtle vignette, and compress for web" and have the agent handle all the technical details.

**US-2: Creative Editing**
As a filmmaker, I want to describe "create a dreamy slow-motion effect with soft color grading" and have the agent chain the appropriate filters.

**US-3: Batch Processing**
As a social media manager, I want to process 20 videos with the same "crop to vertical 9:16, add captions area at bottom" instruction.

**US-4: Preview Before Commit**
As a cautious editor, I want to see a low-res preview of the agent's interpretation before running the full render.

### 2.2 Use Case Examples

| Prompt | Agent Interpretation | FFMPEG Operations |
|--------|---------------------|-------------------|
| "Trim first 5 seconds, make it cinematic" | Remove intro + apply letterbox + color grade | `-ss 5`, crop, eq, colorbalance |
| "Speed up 2x but keep audio pitch" | Time stretch with pitch correction | `setpts=0.5*PTS`, `atempo=2.0` |
| "Make it look like old VHS footage" | Apply noise, chromatic aberration, scanlines | noise, rgbashift, drawbox loop |
| "Extract all frames as PNG" | Frame extraction pipeline | `-vf fps=1 frame_%04d.png` |
| "Stabilize shaky footage" | Video stabilization two-pass | vidstabdetect, vidstabtransform |

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ComfyUI Workflow                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌─────────────────┐    ┌────────────────┐     │
│  │ Load Video   │───▶│  FFMPEGA Agent  │───▶│  Save Video    │     │
│  │    Node      │    │      Node       │    │     Node       │     │
│  └──────────────┘    └────────┬────────┘    └────────────────┘     │
│                               │                                     │
└───────────────────────────────┼─────────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │    FFMPEGA Core       │
                    ├───────────────────────┤
                    │ ┌───────────────────┐ │
                    │ │   LLM Connector   │ │
                    │ │ (Ollama / API)    │ │
                    │ └─────────┬─────────┘ │
                    │           │           │
                    │ ┌─────────▼─────────┐ │
                    │ │   Skill Engine    │ │
                    │ │ (Hybrid System)   │ │
                    │ └─────────┬─────────┘ │
                    │           │           │
                    │ ┌─────────▼─────────┐ │
                    │ │  Python MCP       │ │
                    │ │ (Command DB)      │ │
                    │ └─────────┬─────────┘ │
                    │           │           │
                    │ ┌─────────▼─────────┐ │
                    │ │ FFMPEG Executor   │ │
                    │ │ (Full Trust)      │ │
                    │ └───────────────────┘ │
                    └───────────────────────┘
```

### 3.2 Component Breakdown

#### 3.2.1 LLM Connector (`/core/llm/`)

- **OllamaConnector**: Direct connection to local Ollama instance
  - Streaming response support
  - Model selection (llama3, mistral, codellama, etc.)
  - Context window management
- **APIConnector**: OpenAI/Anthropic compatible API interface
  - API key management
  - Rate limiting and retry logic
  - Response parsing

#### 3.2.2 Skill Engine (`/skills/`)

- **Hybrid Architecture**:
  - **Category Skills**: Low-level operations (trim, resize, filter, encode)
  - **Outcome Skills**: High-level results (cinematic, vintage, stabilize)
- **Skill Registry**: Central registration of all available skills
- **Skill Composer**: Chains skills into multi-step pipelines
- **Parameter Resolver**: Maps LLM output to FFMPEG parameters

#### 3.2.3 Python MCP Server (`/mcp/`)

- **Tools**:
  - `ffmpeg_analyze_video`: Get video metadata and characteristics
  - `ffmpeg_list_skills`: Available editing capabilities
  - `ffmpeg_build_command`: Construct validated command
  - `ffmpeg_execute`: Run the command pipeline
- **Resources**:
  - `ffmpeg://commands`: Full command reference database
  - `ffmpeg://filters`: Filter documentation and examples
  - `ffmpeg://presets`: Pre-built command templates

#### 3.2.4 FFMPEG Executor (`/core/executor/`)

- **CommandBuilder**: Constructs valid FFMPEG command strings
- **ProcessManager**: Handles subprocess execution
- **OutputParser**: Parses FFMPEG output for progress/errors
- **PreviewGenerator**: Creates low-res previews quickly

---

## 4. Skill System Design

### 4.1 Category-Based Skills (Low-Level)

```python
CATEGORY_SKILLS = {
    "temporal": {
        "trim": "Remove portions of video by time",
        "speed": "Adjust playback speed",
        "reverse": "Play video backwards",
        "loop": "Repeat video N times",
        "freeze_frame": "Hold on specific frame"
    },
    "spatial": {
        "resize": "Change video dimensions",
        "crop": "Remove edges of frame",
        "pad": "Add borders/letterbox",
        "rotate": "Rotate video",
        "flip": "Mirror horizontally/vertically"
    },
    "visual": {
        "brightness": "Adjust brightness",
        "contrast": "Adjust contrast",
        "saturation": "Adjust color saturation",
        "hue": "Shift color hue",
        "sharpen": "Increase sharpness",
        "blur": "Apply blur effect",
        "denoise": "Reduce video noise"
    },
    "audio": {
        "volume": "Adjust audio level",
        "normalize": "Normalize audio levels",
        "fade_audio": "Fade in/out audio",
        "remove_audio": "Strip audio track",
        "extract_audio": "Export audio only"
    },
    "encoding": {
        "compress": "Reduce file size",
        "convert": "Change container/codec",
        "bitrate": "Set specific bitrate",
        "quality": "Set quality level (CRF)"
    }
}
```

### 4.2 Outcome-Based Skills (High-Level)

```python
OUTCOME_SKILLS = {
    "cinematic": {
        "description": "Apply cinematic look with letterbox and color grade",
        "pipeline": ["crop:2.35:1", "colorgrade:cinematic", "vignette:soft"]
    },
    "vintage": {
        "description": "Old film look with grain and color shift",
        "pipeline": ["saturation:-20", "noise:film", "vignette:strong", "colorshift:sepia"]
    },
    "vhs": {
        "description": "VHS tape aesthetic",
        "pipeline": ["noise:heavy", "chromatic_aberration", "scanlines", "blur:slight"]
    },
    "timelapse": {
        "description": "Speed up footage dramatically",
        "pipeline": ["speed:10x", "deflicker", "stabilize:light"]
    },
    "slowmo": {
        "description": "Smooth slow motion effect",
        "pipeline": ["speed:0.25x", "interpolate:frames", "motion_blur:subtle"]
    },
    "social_vertical": {
        "description": "Optimize for vertical social media",
        "pipeline": ["crop:9:16", "resize:1080x1920", "compress:web"]
    },
    "stabilize": {
        "description": "Remove camera shake",
        "pipeline": ["vidstab:analyze", "vidstab:transform", "crop:auto"]
    },
    "meme": {
        "description": "Deep-fried meme aesthetic",
        "pipeline": ["saturation:+50", "contrast:+30", "sharpen:extreme", "compress:heavy"]
    }
}
```

### 4.3 Skill Composition Engine

The agent can chain skills together based on prompt analysis:

**User Prompt**: "Make it cinematic but also add some VHS distortion"

**Agent Analysis**:
1. Detected outcome skills: [cinematic, vhs]
2. Resolve conflicts (letterbox vs distortion order)
3. Compose pipeline:
   - Apply cinematic base (letterbox, color grade)
   - Layer VHS effects on top (noise, aberration)
4. Generate final FFMPEG command chain

---

## 5. Node Specifications

### 5.1 FFMPEGAgent Node (Primary)

**Category**: `FFMPEGA/Agent`

| Input | Type | Description |
|-------|------|-------------|
| video | VIDEO | Input video from load node |
| prompt | STRING | Natural language editing instruction |
| llm_model | COMBO | Model selection (ollama models / API) |
| preview_mode | BOOLEAN | Generate preview instead of full render |
| quality_preset | COMBO | Output quality (draft/standard/high/lossless) |

| Output | Type | Description |
|--------|------|-------------|
| video | VIDEO | Processed video output |
| command_log | STRING | FFMPEG commands executed |
| analysis | STRING | Agent's interpretation of prompt |

**Widget UI**:
- Large multiline text input for prompt
- Model selector dropdown
- Preview toggle
- Quality preset selector
- "Show Advanced" expandable section

### 5.2 VideoPreview Node

**Category**: `FFMPEGA/Utils`

| Input | Type | Description |
|-------|------|-------------|
| video | VIDEO | Input video |
| preview_resolution | COMBO | 360p/480p/720p |
| frame_skip | INT | Process every Nth frame |

| Output | Type | Description |
|--------|------|-------------|
| preview | VIDEO | Low-res preview video |
| thumbnail | IMAGE | First frame as image |

### 5.3 BatchProcessor Node

**Category**: `FFMPEGA/Batch`

| Input | Type | Description |
|-------|------|-------------|
| video_folder | STRING | Path to folder with videos |
| prompt | STRING | Editing instruction for all |
| output_folder | STRING | Destination folder |
| file_pattern | STRING | Glob pattern (*.mp4, *.mov) |

| Output | Type | Description |
|--------|------|-------------|
| processed_count | INT | Number of videos processed |
| output_paths | STRING | List of output file paths |
| error_log | STRING | Any errors encountered |

---

## 6. LLM Integration Design

### 6.1 System Prompt Template

```
You are FFMPEGA, an expert video editing agent. Your role is to interpret
natural language video editing requests and translate them into precise
FFMPEG operations.

## Available Skills
{skill_registry_dump}

## Input Video Analysis
{video_metadata}

## Your Task
Given the user's editing request, you must:
1. Analyze the request to identify required operations
2. Select appropriate skills from the registry
3. Determine optimal operation order
4. Specify exact parameters for each operation
5. Output a structured pipeline specification

## Output Format
Respond with a JSON object:
{
  "interpretation": "Brief explanation of understanding",
  "pipeline": [
    {"skill": "skill_name", "params": {...}},
    ...
  ],
  "warnings": ["Any potential issues or limitations"]
}
```

### 6.2 Ollama Configuration

```python
OLLAMA_CONFIG = {
    "default_model": "llama3.1:8b",
    "recommended_models": [
        "llama3.1:8b",      # Good balance
        "llama3.1:70b",     # Best quality
        "mistral:7b",       # Fast alternative
        "codellama:13b",    # Good for technical parsing
        "deepseek-coder:6.7b"  # Code-focused
    ],
    "context_window": 8192,
    "temperature": 0.3,  # Lower for more deterministic
    "base_url": "http://localhost:11434"
}
```

### 6.3 API Configuration

```python
API_CONFIG = {
    "providers": {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini"]
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "models": ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"]
        },
        "custom": {
            "base_url": "{user_defined}",
            "models": "{user_defined}"
        }
    },
    "timeout": 30,
    "max_retries": 3
}
```

---

## 7. MCP Server Specification

### 7.1 Python MCP Implementation

```python
# /mcp/server.py
from mcp.server import Server
from mcp.types import Tool, Resource

class FFMPEGAMCPServer:
    """Python-based MCP server for FFMPEG command database."""

    tools = [
        Tool(
            name="analyze_video",
            description="Analyze input video properties",
            parameters={
                "video_path": "Path to video file"
            }
        ),
        Tool(
            name="list_skills",
            description="List available editing skills",
            parameters={
                "category": "Optional category filter"
            }
        ),
        Tool(
            name="build_pipeline",
            description="Build FFMPEG command pipeline from skill list",
            parameters={
                "skills": "List of skill specifications",
                "input_path": "Input video path",
                "output_path": "Output video path"
            }
        ),
        Tool(
            name="execute_pipeline",
            description="Execute built pipeline",
            parameters={
                "pipeline_id": "Pipeline to execute"
            }
        )
    ]

    resources = [
        Resource(
            uri="ffmpeg://commands/reference",
            name="FFMPEG Command Reference",
            description="Complete FFMPEG command documentation"
        ),
        Resource(
            uri="ffmpeg://filters/list",
            name="FFMPEG Filters",
            description="Available video/audio filters"
        ),
        Resource(
            uri="ffmpeg://skills/registry",
            name="Skill Registry",
            description="All registered editing skills"
        )
    ]
```

### 7.2 Command Database Structure

```python
FFMPEG_COMMAND_DB = {
    "filters": {
        "video": {
            "scale": {
                "syntax": "scale=w:h",
                "description": "Resize video",
                "examples": [
                    "scale=1920:1080",
                    "scale=-1:720",  # Maintain aspect
                    "scale=iw/2:ih/2"  # Half size
                ]
            },
            "crop": {
                "syntax": "crop=w:h:x:y",
                "description": "Crop video region",
                "examples": [
                    "crop=1280:720:0:180",
                    "crop=in_w:in_w*9/16"  # Vertical crop
                ]
            },
            # ... 50+ more filters
        },
        "audio": {
            "volume": {...},
            "atempo": {...},
            # ...
        }
    },
    "codecs": {
        "video": {
            "libx264": {...},
            "libx265": {...},
            "libvpx-vp9": {...}
        },
        "audio": {
            "aac": {...},
            "libmp3lame": {...}
        }
    },
    "presets": {
        "web_optimized": "-c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k",
        "high_quality": "-c:v libx264 -crf 18 -preset slow -c:a aac -b:a 256k",
        "quick_preview": "-c:v libx264 -crf 28 -preset ultrafast -an"
    }
}
```

---

## 8. Directory Structure

```
ComfyUI-FFMPEGA/
├── __init__.py                 # ComfyUI entry point
├── pyproject.toml              # Package configuration
├── requirements.txt            # Python dependencies
├── README.md                   # Documentation
├── LICENSE                     # MIT License
│
├── nodes/                      # ComfyUI node definitions
│   ├── __init__.py
│   ├── agent_node.py           # FFMPEGAgent node
│   ├── preview_node.py         # VideoPreview node
│   └── batch_node.py           # BatchProcessor node
│
├── core/                       # Core functionality
│   ├── __init__.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract LLM interface
│   │   ├── ollama.py           # Ollama connector
│   │   └── api.py              # OpenAI/Anthropic API
│   ├── executor/
│   │   ├── __init__.py
│   │   ├── command_builder.py  # FFMPEG command construction
│   │   ├── process_manager.py  # Subprocess handling
│   │   └── preview.py          # Preview generation
│   └── video/
│       ├── __init__.py
│       ├── analyzer.py         # Video metadata extraction
│       └── formats.py          # Format handling
│
├── skills/                     # Skill system
│   ├── __init__.py
│   ├── registry.py             # Skill registration
│   ├── composer.py             # Skill pipeline composition
│   ├── category/               # Category-based skills
│   │   ├── temporal.py
│   │   ├── spatial.py
│   │   ├── visual.py
│   │   ├── audio.py
│   │   └── encoding.py
│   └── outcome/                # Outcome-based skills
│       ├── cinematic.py
│       ├── vintage.py
│       ├── social.py
│       └── effects.py
│
├── mcp/                        # MCP server
│   ├── __init__.py
│   ├── server.py               # MCP server implementation
│   ├── tools.py                # MCP tool definitions
│   ├── resources.py            # MCP resource definitions
│   └── database/
│       ├── commands.py         # FFMPEG command database
│       ├── filters.py          # Filter documentation
│       └── presets.py          # Pre-built presets
│
├── prompts/                    # LLM prompt templates
│   ├── system.py               # System prompt
│   ├── analysis.py             # Video analysis prompts
│   └── generation.py           # Command generation prompts
│
├── web/                        # Frontend assets (optional)
│   └── ffmpega_ui.js           # Custom UI widgets
│
└── tests/                      # Test suite
    ├── test_executor.py
    ├── test_skills.py
    ├── test_llm.py
    └── fixtures/
        └── sample_videos/
```

---

## 9. Dependencies

### 9.1 Required Dependencies

```txt
# requirements.txt

# Core
ffmpeg-python>=0.2.0      # FFMPEG Python bindings
imageio>=2.31.0           # Video frame handling
imageio-ffmpeg>=0.4.8     # FFMPEG plugin for imageio
numpy>=1.24.0             # Array processing
pillow>=10.0.0            # Image handling

# LLM Integration
httpx>=0.25.0             # Async HTTP client
ollama>=0.1.0             # Ollama Python SDK (optional)

# MCP Server
mcp>=1.0.0                # Model Context Protocol SDK

# Utilities
pydantic>=2.0.0           # Data validation
python-dotenv>=1.0.0      # Environment configuration
```

### 9.2 System Requirements

- **FFMPEG**: Must be installed and in PATH
- **Python**: 3.10+
- **Ollama**: (Optional) For local LLM inference
- **GPU**: (Optional) For hardware-accelerated encoding

---

## 10. Configuration

### 10.1 User Configuration File

```yaml
# config.yaml (in ComfyUI user data)

ffmpega:
  # LLM Settings
  llm:
    provider: "ollama"  # ollama | openai | anthropic | custom
    model: "llama3.1:8b"
    api_key: ""  # For API providers
    base_url: "http://localhost:11434"  # For Ollama or custom

  # FFMPEG Settings
  ffmpeg:
    path: "ffmpeg"  # Or full path
    hardware_accel: "auto"  # auto | cuda | vaapi | none
    default_preset: "medium"

  # Preview Settings
  preview:
    resolution: 480
    frame_skip: 2
    format: "mp4"

  # Batch Processing
  batch:
    max_concurrent: 4
    continue_on_error: true
    output_naming: "{original}_edited"
```

---

## 11. Workflow Examples

### 11.1 Basic Single Edit

```
[Load Video] ──▶ [FFMPEGA Agent] ──▶ [Save Video]
                      │
                 prompt: "Add letterbox
                  and warm color grade"
```

### 11.2 Preview Before Commit

```
[Load Video] ──▶ [FFMPEGA Agent] ──▶ [Preview Image]
                      │                    │
                 preview_mode: true        └──▶ [View & Approve]
                                                      │
                                                      ▼
                 [FFMPEGA Agent] ──▶ [Save Video]
                 preview_mode: false
```

### 11.3 Batch Processing

```
[Batch Processor] ──▶ [Progress Display]
        │
   folder: "/videos"
   prompt: "Compress for web,
            add watermark"
   pattern: "*.mp4"
```

---

## 12. Error Handling

### 12.1 Error Categories

| Category | Example | Handling |
|----------|---------|----------|
| LLM Error | Model not found, timeout | Retry with fallback model |
| Parse Error | Invalid skill output | Re-prompt with correction |
| FFMPEG Error | Invalid filter syntax | Log and report to user |
| File Error | Input not found | Fail with clear message |
| Resource Error | Out of disk space | Abort with warning |

### 12.2 Error Response Format

```python
class FFMPEGAError:
    category: str       # "llm" | "parse" | "ffmpeg" | "file" | "resource"
    message: str        # Human-readable message
    details: dict       # Technical details
    recoverable: bool   # Can retry?
    suggestion: str     # Recommended action
```

---

## 13. Future Considerations (Post-V1)

- **Session Memory**: Remember context for iterative refinement
- **Undo/History**: Track and rollback edits
- **Visual Timeline**: Node-based timeline editing
- **Audio Sync**: Automatic beat detection and sync
- **Template Library**: Shareable skill templates
- **Cloud Processing**: Offload heavy renders
- **Real-time Preview**: Live preview during editing

---

## 14. Implementation Phases

### Phase 1: Foundation (Week 1)
- Project structure setup
- Basic FFMPEG executor
- Video analyzer (metadata extraction)

### Phase 2: Skill System (Week 2)
- Skill registry architecture
- Category skills implementation
- Outcome skills implementation
- Skill composer

### Phase 3: LLM Integration (Week 3)
- Ollama connector
- API connector (OpenAI/Anthropic)
- Prompt engineering system
- Response parsing

### Phase 4: MCP Server (Week 4)
- Python MCP server setup
- Tool implementations
- Resource definitions
- Command database

### Phase 5: ComfyUI Nodes (Week 5)
- FFMPEGAgent node
- VideoPreview node
- BatchProcessor node
- UI widgets

### Phase 6: Integration & Testing (Week 6)
- End-to-end testing
- Error handling refinement
- Documentation
- Example workflows

---

## 15. Verification Plan

### 15.1 Unit Tests
- Test FFMPEG command builder with various inputs
- Test skill registry and composition
- Test LLM response parsing

### 15.2 Integration Tests
- Test full pipeline from prompt to video output
- Test batch processing with multiple files
- Test preview generation

### 15.3 Manual Verification
1. Install node in ComfyUI
2. Load sample video
3. Connect to FFMPEGA Agent node
4. Enter test prompts:
   - "Make it 50% smaller"
   - "Add cinematic letterbox"
   - "Speed up 2x"
5. Verify output matches expectations

---

## Appendix A: Reference Projects

- **Remotion**: Declarative/composable video editing patterns
- **ComfyUI-VisualCLI**: MCP integration reference
- **ComfyUI-ShaderNoiseKSampler**: Complex node structure reference
- **ComfyUI-DiscordSend**: Video handling node reference

---

## Appendix B: FFMPEG Quick Reference

Common operations the agent should handle:

```bash
# Resize
ffmpeg -i input.mp4 -vf "scale=1920:1080" output.mp4

# Trim
ffmpeg -i input.mp4 -ss 00:00:05 -to 00:00:30 output.mp4

# Speed up
ffmpeg -i input.mp4 -filter:v "setpts=0.5*PTS" -filter:a "atempo=2.0" output.mp4

# Add letterbox
ffmpeg -i input.mp4 -vf "pad=iw:iw*9/16:(ow-iw)/2:(oh-ih)/2" output.mp4

# Color grade
ffmpeg -i input.mp4 -vf "eq=contrast=1.2:brightness=0.1:saturation=0.9" output.mp4

# Compress
ffmpeg -i input.mp4 -c:v libx264 -crf 23 -preset medium output.mp4

# Stabilize (two-pass)
ffmpeg -i input.mp4 -vf vidstabdetect -f null -
ffmpeg -i input.mp4 -vf vidstabtransform output.mp4
```

---

**Document Version**: 1.0  
**Created**: 2026-01-29  
**Last Updated**: 2026-01-29
