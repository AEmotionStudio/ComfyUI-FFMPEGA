# 🤖 LLM Configuration

*Part of the [ComfyUI-FFMPEGA](../README.md) documentation.*

> **Tested with:** FFMPEGA has been primarily tested using **Gemini CLI** and **Qwen3 8B** (via Ollama). Results may vary with other models.
>
> **Author's pick:** The CLI connectors (especially **Gemini CLI**) have been the most reliable option in my experience — they handle tool-calling, structured output, and long context exceptionally well. Highly recommended if you have access.

### Choosing a Model

FFMPEGA works best with models that have **strong JSON output and instruction-following abilities**. The agent sends a structured prompt and expects a valid JSON pipeline back — models with tool-calling or function-calling capabilities tend to perform best.

**Things to keep in mind:**
- **Some models work better than others** — larger models and those trained for structured output (JSON/tool-calling) produce more reliable results
- **Some models may need more retries** — if the agent fails to parse the response, try running the same prompt again. Smaller models occasionally return malformed JSON on the first try
- **Find what works best for you** — experiment with different models to find the right balance of speed, quality, and reliability for your hardware

### Ollama (Local — Free)
The default option. Runs locally, no API key needed.

**Install Ollama:** Download from [ollama.com/download](https://ollama.com/download) (available for Linux, macOS, and Windows).

```bash
# Start Ollama (all platforms)
ollama serve

# Pull a model
ollama pull qwen3:8b
```

> **Windows users:** After installing Ollama, the `ollama` command is available in both PowerShell and Command Prompt. Ollama also runs as a system tray app.

**Recommended local models (≤30B, consumer GPU friendly):**
| Model | Size | Speed | Notes |
| :--- | :--- | :--- | :--- |
| `qwen3:8b` | 8B | ⚡ Fast | **Tested** — excellent structured output, native tool-calling |
| `qwen3-vl` | 8B | ⚡ Fast | **Tested** — multimodal vision-language model, sees video frames |
| `qwen3:14b` | 14B | ⚡ Fast | Sweet spot of speed and quality, tools + thinking tags |
| `qwen3:30b` | 30B | 🔄 Medium | Best Qwen under 30B, needs 16GB+ VRAM |
| `qwen2.5:14b` | 14B | ⚡ Fast | Top IFEval scores, strong instruction following |
| `deepseek-r1:14b` | 14B | ⚡ Fast | Reasoning model — verifies its own tool calls, very reliable |
| `mistral-nemo` | 12B | ⚡ Fast | NVIDIA + Mistral collab, 128k context, great reasoning |
| `mistral-small3.2` | 24B | 🔄 Medium | Native function calling, 128k context |
| `phi4` | 14B | ⚡ Fast | Microsoft reasoning SLM, rivals larger models in logic |
| `gemma3:12b` | 12B | ⚡ Fast | High reasoning scores, 128k context |
| `llama3.3:8b` | 8B | ⚡ Fast | Reliable tool-calling, large ecosystem |

> **Tip:** On the [Ollama library](https://ollama.com/library), look for models with a **tools** tag — this indicates native tool/function-calling support, which produces the best results with FFMPEGA.

### Gemini CLI (Free with any Google Account)

Use the [Gemini CLI](https://github.com/google-gemini/gemini-cli) to run Gemini models without an API key. Works with any Google account.

**Install:**

| Platform | Command |
| :--- | :--- |
| **Linux / macOS** | `npm install -g @google/gemini-cli` |
| **Windows (PowerShell)** | `npm install -g @google/gemini-cli` |

> **Tip:** You can also use `pnpm add -g` or `yarn global add` if you prefer.

**Authenticate** (first time only):
```bash
gemini
```
This opens a browser to sign in with your Google account.

**Use in FFMPEGA:**
```
llm_model: gemini-cli
```

No API key is needed — authentication is handled by the CLI. Select `gemini-cli` from the model dropdown in the node.

> **Note:** The Gemini CLI runs as a subprocess and is sandboxed to the custom node directory for security. On Windows, `gemini.cmd` is also detected automatically.

#### Plans & Usage Limits

| Plan | Rate Limit | Daily Limit | Models | Cost |
| :--- | :--- | :--- | :--- | :--- |
| **Free** (Google login) | 60 req/min | 1,000 req/day | Gemini model family (Pro + Flash) | Free |
| **Free** (API key only) | 10 req/min | 250 req/day | Flash only | Free |
| **Code Assist Standard** | 120 req/min | 1,500 req/day | Gemini model family | Paid |
| **Code Assist Enterprise** | 120 req/min | 2,000 req/day | Gemini model family | Paid |
| **Google AI Pro** | Higher | Higher | Full Gemini family | $19.99/mo |

> **Tip:** Sign in with a Google account (free) for the best experience — 1,000 requests/day with access to Pro and Flash models. An unpaid API key limits you to 250/day on Flash only.

#### Available Models

The Gemini CLI auto-selects the best model, but the following are available:

| Model | Best For |
| :--- | :--- |
| Gemini 2.5 Pro | Complex reasoning, creative tasks |
| Gemini 2.5 Flash | Fast responses, high throughput |
| Gemini 2.5 Flash-Lite | Maximum speed, lowest cost |
| Gemini 3 Pro | Most capable, advanced reasoning |
| Gemini 3 Flash | Fast + capable, good balance |

> Free tier may auto-switch to Flash models when Pro quota is exhausted.

### Claude Code CLI (Free with Anthropic Account)

Use the [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) as a local LLM backend. Uses its own authentication — no API key needed in FFMPEGA.

**Install:**

| Platform | Command |
| :--- | :--- |
| **Linux / macOS** | `npm install -g @anthropic-ai/claude-code` |
| **Windows (PowerShell)** | `npm install -g @anthropic-ai/claude-code` |

> **Tip:** You can also use `pnpm add -g` or `yarn global add` if you prefer.

**Authenticate** (first time only):
```bash
claude
```
This opens a browser to sign in with your Anthropic account.

**Use in FFMPEGA:**
```
llm_model: claude-cli
```

Auto-detected on PATH. Select `claude-cli` from the model dropdown.

### Cursor Agent CLI

Use [Cursor's CLI](https://docs.cursor.com) in agent mode as an LLM backend.

**Install (all platforms):**
Open Cursor IDE → Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) → "Install 'cursor' command"

**Start the agent:**
```bash
agent
```

**Use in FFMPEGA:**
```
llm_model: cursor-agent
```

Auto-detected on PATH. Select `cursor-agent` from the model dropdown.

### Qwen Code CLI (Free — 2,000 requests/day)

Use [Qwen Code](https://qwenlm.github.io/qwen-code-docs/) as a free LLM backend. Powered by Qwen3-Coder with 2,000 free requests/day via OAuth — no credit card required.

**Install:**

| Platform | Command |
| :--- | :--- |
| **Linux / macOS** | `npm install -g @qwen-code/qwen-code@latest` |
| **Windows (PowerShell)** | `npm install -g @qwen-code/qwen-code@latest` |

> **Tip:** You can also use `pnpm add -g` or `yarn global add` if you prefer.

**Authenticate** (first time only):
```bash
qwen
```
Select "Qwen OAuth (Free)" and follow the browser prompts to sign in.

**Use in FFMPEGA:**
```
llm_model: qwen-cli
```

Auto-detected on PATH. Select `qwen-cli` from the model dropdown.

### 👁️ CLI Agent Vision Support

When [Frame Extraction](../SKILLS_REFERENCE.md) is used, FFMPEGA saves extracted frames to a `_vision_frames/` directory and passes the frame paths to the CLI agent. Agents with vision support can **see and analyze the actual frame images** to make better editing decisions.

| CLI Agent | Vision Support | Notes |
| :--- | :--- | :--- |
| **Gemini CLI** | ✅ Yes | `read_file` converts images to base64 for multimodal analysis |
| **Claude Code CLI** | ✅ Yes | Native image reading and description |
| **Cursor Agent CLI** | ✅ Yes | Native image reading and description |
| **Qwen Code CLI** | ❌ Not yet | [Known issue](https://github.com/QwenLM/qwen-code/issues) — `read_file` returns raw binary instead of interpreting images. Vision is listed as a planned feature. |

> **Note:** Agents without vision support still receive the frame file paths and can use video metadata (duration, resolution, FPS) from `analyze_video` to make editing decisions. When Qwen fixes their vision support upstream, it will work automatically since the frame paths are already passed correctly.

> ⚠️ **Important:** The `_vision_frames/` directory must **not** be listed in `.gitignore` or `.git/info/exclude` — CLI agents respect these ignore patterns and will be unable to read the frames. FFMPEGA's `cleanup_vision_frames()` automatically deletes the directory after each pipeline run.

### Custom Model

Select **`custom`** from the model dropdown and type any Ollama model name in the `custom_model` field (e.g. `qwen3:14b`). The dropdown only lists models installed on the local Ollama server, so this is how you reach a model it doesn't show — for example one on a remote server set via `ollama_url`.

### 📊 Token Usage Tracking

Monitor your LLM token consumption with opt-in usage tracking. Enable via two toggles on the node:

| Toggle | Default | What It Does |
| :--- | :--- | :--- |
| `track_tokens` | Off | Prints a formatted usage summary to the console after each run |
| `log_usage` | Off | Appends a JSON entry to `usage_log.jsonl` for cumulative tracking |

**Token data sources by connector:**

| Connector | Source | Estimated? |
| :--- | :--- | :--- |
| Ollama | Native API (`prompt_eval_count` / `eval_count`) | No |
| **Gemini CLI** | JSON output via `-o json` | No |
| **Claude CLI** | JSON output via `--output-format json` | No |
| Other CLIs | Character-based estimation (~4 chars/token) | Yes |

When enabled, the **analysis output** includes a usage breakdown:

```
Token Usage:
  Prompt tokens:     4,200
  Completion tokens: 1,800
  Total tokens:      6,000
  LLM calls:         5
  Tool calls:        3
  Elapsed:           12.4s
```

The `usage_log.jsonl` file stores one JSON object per run for historical analysis. It is gitignored by default.

---
