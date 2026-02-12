# Custom Skills Guide

FFMPEGA supports user-defined skills via YAML files and **skill packs** — git repositories you can install with a single `git clone`. No Python required for simple skills.

## Quick Start

1. Create a `.yaml` file in the `custom_skills/` folder
2. Restart ComfyUI
3. Your skill is available to the AI agent

```yaml
# custom_skills/dreamy_blur.yaml
name: dreamy_blur
description: "Soft dreamy blur with glow"
category: visual
tags: [dream, blur, soft, glow]
examples:
  - "dreamy_blur - Add dreamy blur"
  - "dreamy_blur:radius=10 - Strong dreamy blur"

parameters:
  radius:
    type: int
    description: "Blur radius"
    default: 5
    min: 1
    max: 30

ffmpeg_template: "gblur=sigma={radius},eq=brightness=0.06"
```

---

## YAML Schema Reference

| Field | Required | Description |
|-------|----------|-------------|
| `name` | ✅ | Unique skill name (lowercase, underscores) |
| `description` | ✅ | What the skill does (shown to the AI) |
| `category` | | One of: `temporal`, `spatial`, `visual`, `audio`, `encoding`, `outcome`, `custom` (default: `custom`) |
| `tags` | | Search keywords for the AI to find this skill |
| `aliases` | | Alternative names that also register this skill |
| `examples` | | Example usage strings (shown to the AI) |
| `parameters` | | Parameter definitions (see below) |
| `ffmpeg_template` | ⚡ | FFmpeg filter string with `{param}` placeholders |
| `pipeline` | ⚡ | List of existing skills to chain (alternative to template) |

> ⚡ Provide **either** `ffmpeg_template` or `pipeline`, not both.

### Parameter Fields

```yaml
parameters:
  my_param:
    type: float          # int, float, string, bool, choice, time, color
    description: "..."   # Shown to the AI
    default: 0.5         # Default value (makes param optional)
    required: false      # Default: false
    min: 0.0             # For int/float
    max: 1.0             # For int/float
    choices: [a, b, c]   # For choice type only
```

### Template Skills

Use `ffmpeg_template` for skills that map to a single FFmpeg filter:

```yaml
name: soft_focus
description: "Soft focus portrait effect"
category: visual
ffmpeg_template: "gblur=sigma={radius},unsharp=5:5:{sharpen}:5:5:0"

parameters:
  radius:
    type: float
    default: 3.0
  sharpen:
    type: float
    default: 0.5
```

The template uses `{param_name}` placeholders that are replaced with parameter values. The system auto-detects whether it's a video filter, audio filter, or output option:
- Starts with `-` → output option
- Category is `audio` → audio filter
- Otherwise → video filter

### Pipeline Skills

Use `pipeline` to chain existing built-in or custom skills:

```yaml
name: film_burn
description: "Film burn / light leak effect"
category: creative

parameters:
  intensity:
    type: float
    default: 0.5

pipeline:
  - "brightness:value={intensity}"
  - "colorbalance:rs={intensity},gs=0.05,bs=-0.1"
  - "saturation:value=1.2"
```

The format for each step is `skill_name:param1=val1,param2=val2`. Parameters from the parent skill are substituted via `{param}` syntax.

---

## Skill Packs

Skill packs are directories (typically git repos) that group related skills together with optional Python handlers for complex logic.

### Installing a Skill Pack

```bash
cd custom_skills/
git clone https://github.com/someone/ffmpega-retro-pack retro-pack
```

Restart ComfyUI — all skills from the pack are available.

### Skill Pack Structure

```
retro-pack/
├── pack.yaml              # Optional metadata
├── skills/
│   ├── vhs_pro.yaml       # YAML skill definitions
│   ├── betamax.yaml
│   └── crt_monitor.yaml
└── handlers.py            # Optional: Python handlers
```

#### `pack.yaml` (optional)

```yaml
name: retro-pack
author: "Your Name"
version: "1.0.0"
description: "Advanced retro and analog video effects"
```

#### `handlers.py` (optional)

For skills that need complex filter logic beyond simple templates:

```python
"""Python handlers for the retro-pack skill pack.

Each function name must match a skill 'name' from this pack's YAML files.
Functions receive the params dict and return a tuple of filter lists.
"""

def vhs_pro(params):
    """VHS effect with dynamic tracking lines.
    
    Returns: (video_filters, audio_filters, output_options)
    """
    lines = params.get("tracking_lines", 3)
    noise = params.get("noise", 20)
    return (
        [f"noise=alls={noise}:allf=t+u", "eq=contrast=1.1:saturation=0.8"],
        [],   # no audio filters
        [],   # no output options
    )
```

Handler return format:
- **3-tuple**: `(video_filters, audio_filters, output_options)` — most common
- **4-tuple**: `+ filter_complex` string
- **5-tuple**: `+ input_options` list

> **Priority**: If a YAML skill has both `ffmpeg_template`/`pipeline` AND a matching Python handler, the template/pipeline takes priority. Handlers are only used for skills with no template or pipeline defined.

### Creating a Skill Pack

1. Create a directory in `custom_skills/`:
   ```
   mkdir -p custom_skills/my-pack/skills
   ```

2. Add YAML skills in `skills/`:
   ```yaml
   # custom_skills/my-pack/skills/my_effect.yaml
   name: my_effect
   description: "My custom effect"
   category: custom
   ffmpeg_template: "eq=brightness=0.1"
   ```

3. *(Optional)* Add `pack.yaml` for metadata

4. *(Optional)* Add `handlers.py` for complex skills

5. To share: push to GitHub and others can `git clone` it

---

## Examples

Two example skills are shipped in `custom_skills/examples/`:

- **`warm_glow.yaml`** — Simple template skill (colorbalance)
- **`film_burn.yaml`** — Pipeline composite skill (chains brightness + colorbalance + saturation)

Study these to understand the format, then create your own!

---

## Tips

- **Naming**: Use `snake_case` for skill names — `my_cool_effect`, not `My Cool Effect`
- **Tags matter**: The AI uses tags to find skills. Add synonyms and related terms
- **Test first**: Try your FFmpeg filter manually before putting it in a YAML
- **Aliases**: Add common alternative names so the AI finds your skill more easily
- **Categories**: Use the right category so skills appear in the correct section
- **Restart**: You must restart ComfyUI after adding/modifying custom skills
