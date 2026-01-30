# ComfyUI-FFMPEGA

An intelligent FFMPEG agent node for ComfyUI that transforms natural language video editing prompts into precise, automated video transformations.

## Features

- **Natural Language Editing**: Describe what you want in plain text
- **AI-Powered Pipeline Generation**: Automatically translates prompts to FFMPEG commands
- **Comprehensive Skill System**: 50+ video editing operations organized by category
- **Multiple LLM Support**: Works with Ollama (local), OpenAI, and Anthropic
- **Batch Processing**: Process multiple videos with the same instruction
- **Preview Generation**: Quick previews before full renders

## Installation

### Requirements

- Python 3.10+
- FFMPEG installed and in PATH
- ComfyUI
- (Optional) Ollama for local LLM inference

### Install

1. Clone this repository into your ComfyUI custom_nodes folder:
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/your-repo/ComfyUI-FFMPEGA.git
```

2. Install dependencies:
```bash
cd ComfyUI-FFMPEGA
pip install -r requirements.txt
```

3. Restart ComfyUI

## Quick Start

### Basic Usage

1. Add an **FFMPEG Agent** node to your workflow
2. Connect a video path or use the input field
3. Enter a natural language prompt like:
   - "Make this video 720p and add a cinematic letterbox"
   - "Speed up 2x but keep the audio pitch normal"
   - "Create a vintage VHS look with grain and color shift"
4. Select your LLM model (default: Ollama llama3.1:8b)
5. Run the workflow

### Example Prompts

| Prompt | What it does |
|--------|--------------|
| "Trim first 5 seconds, make it cinematic" | Removes intro, adds letterbox and color grade |
| "Speed up 2x but keep audio pitch" | Doubles speed with pitch correction |
| "Make it look like old VHS footage" | Adds noise, color shift, scan lines |
| "Extract all frames as PNG" | Frame extraction pipeline |
| "Compress for web, add watermark" | Web-optimized encoding with overlay |

## Nodes

### FFMPEG Agent
The main node for natural language video editing.

**Inputs:**
- `video_path`: Path to input video
- `prompt`: Natural language editing instruction
- `llm_model`: Model selection (Ollama/OpenAI/Anthropic)
- `quality_preset`: Output quality (draft/standard/high/lossless)
- `preview_mode`: Generate quick preview instead of full render

**Outputs:**
- `video`: Path to processed video
- `command_log`: FFMPEG commands executed
- `analysis`: Agent's interpretation of the prompt

### Video Preview
Generate low-resolution previews and thumbnails.

### Batch Processor
Process multiple videos with the same editing instruction.

## Skill System

FFMPEGA includes a comprehensive skill system organized into categories:

### Category Skills (Low-Level)

**Temporal:**
- `trim` - Remove portions by time
- `speed` - Adjust playback speed
- `reverse` - Play backwards
- `loop` - Repeat video
- `fps` - Change frame rate

**Spatial:**
- `resize` - Change dimensions
- `crop` - Remove edges
- `pad` - Add borders/letterbox
- `rotate` - Rotate video
- `flip` - Mirror horizontally/vertically

**Visual:**
- `brightness`, `contrast`, `saturation` - Color adjustments
- `sharpen`, `blur`, `denoise` - Detail adjustments
- `vignette`, `fade` - Effects
- `noise`, `curves` - Advanced effects

**Audio:**
- `volume` - Adjust level
- `normalize` - Consistent loudness
- `fade_audio` - Audio fades
- `remove_audio` - Strip audio

**Encoding:**
- `compress` - Reduce file size
- `convert` - Change codec
- `quality` - Set CRF/preset

### Outcome Skills (High-Level)

- `cinematic` - Letterbox + color grade
- `vintage` - Old film look
- `vhs` - VHS tape aesthetic
- `social_vertical` - TikTok/Reels format
- `youtube` - YouTube optimized
- `stabilize` - Remove camera shake
- `timelapse` - Speed up footage
- `slowmo` - Smooth slow motion

## LLM Configuration

### Ollama (Default)
```python
# Uses local Ollama instance
llm_model = "llama3.1:8b"
ollama_url = "http://localhost:11434"
```

Recommended models:
- `llama3.1:8b` - Good balance
- `llama3.1:70b` - Best quality
- `mistral:7b` - Fast alternative
- `codellama:13b` - Technical parsing

### OpenAI
```python
llm_model = "gpt-4o-mini"
api_key = "your-openai-key"
```

### Anthropic
```python
llm_model = "claude-3-5-haiku-20241022"
api_key = "your-anthropic-key"
```

## API / MCP Server

FFMPEGA includes an MCP (Model Context Protocol) server for programmatic access:

```python
from mcp.server import get_server

server = get_server()

# List available skills
skills = await server.call_tool("list_skills", {})

# Build a pipeline
result = await server.call_tool("build_pipeline", {
    "skills": [
        {"name": "resize", "params": {"width": 1280, "height": 720}},
        {"name": "compress", "params": {"preset": "medium"}}
    ],
    "input_path": "/input.mp4",
    "output_path": "/output.mp4"
})
```

## Development

### Running Tests
```bash
pytest tests/
```

### Project Structure
```
ComfyUI-FFMPEGA/
├── __init__.py          # ComfyUI entry point (NODE_CLASS_MAPPINGS)
├── nodes/               # ComfyUI node definitions
│   ├── agent_node.py    # FFMPEGAgent main node
│   ├── preview_node.py  # Preview and info nodes
│   └── batch_node.py    # Batch processing nodes
├── core/                # Core functionality
│   ├── llm/             # LLM connectors (Ollama, OpenAI, Anthropic)
│   ├── executor/        # FFMPEG command building & execution
│   └── video/           # Video analysis & formats
├── skills/              # Skill system
│   ├── registry.py      # Skill registration
│   ├── composer.py      # Pipeline composition
│   ├── category/        # Low-level skills (temporal, spatial, visual, audio, encoding)
│   └── outcome/         # High-level skills (cinematic, vintage, social, effects)
├── mcp/                 # MCP server for programmatic access
├── prompts/             # LLM prompt templates
├── js/                  # Custom ComfyUI UI widgets
└── tests/               # Test suite
```

## Troubleshooting

### FFMPEG Not Found
Ensure FFMPEG is installed and in your system PATH:
```bash
ffmpeg -version
```

### Ollama Connection Failed
Make sure Ollama is running:
```bash
ollama serve
```

### Model Not Found
Pull the required model:
```bash
ollama pull llama3.1:8b
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please read our contributing guidelines and submit pull requests.

## Acknowledgments

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) - The foundation
- [FFMPEG](https://ffmpeg.org/) - The video processing backbone
- [Ollama](https://ollama.ai/) - Local LLM inference
