---
description: How to add a new video editing skill to FFMPEGA
---

# Adding a New Skill to FFMPEGA

## Overview
FFMPEGA uses a skill-based system where each editing operation (brightness, blur, speed, etc.) is a registered `Skill` object that maps to FFMPEG filters.

## Steps

### 1. Choose the right location
- **Category skills** (basic operations): `skills/category/` — temporal, spatial, visual, audio, encoding
- **Outcome skills** (pre-built effect chains): `skills/outcome/` — cinematic, vintage, motion, transitions

### 2. Define the skill
Add to the appropriate `register_skills()` function:

```python
registry.register(Skill(
    name="my_effect",
    category=SkillCategory.VISUAL,  # or OUTCOME, TEMPORAL, etc.
    description="Clear description of what the effect does",
    parameters=[
        SkillParameter(
            name="amount",
            type=ParameterType.FLOAT,
            description="Effect strength",
            required=False,
            default=1.0,
            min_value=0.0,
            max_value=3.0,
        ),
        SkillParameter(
            name="mode",
            type=ParameterType.CHOICE,
            description="Effect mode",
            required=False,
            default="normal",
            choices=["normal", "strong", "subtle"],
        ),
    ],
    examples=[
        "my_effect - Apply with defaults",
        "my_effect:amount=2.0,mode=strong - Strong effect",
    ],
    tags=["effect", "visual", "relevant", "keywords"],
))
```

### 3. Add the FFMPEG handler
In `skills/composer.py`, find the `_builtin_skill_filters()` method and add:

```python
elif skill_name == "my_effect":
    amount = float(params.get("amount", 1.0))
    mode = params.get("mode", "normal")
    # Build the FFMPEG filter string
    video_filters.append(f"some_ffmpeg_filter={amount}")
```

The handler must populate one or more of:
- `video_filters` — FFMPEG `-vf` filters (list of strings)
- `audio_filters` — FFMPEG `-af` filters (list of strings)
- `output_options` — FFMPEG output options like codec settings

### 4. Register the module (new files only)
If you created a new file, add it to:
- `skills/registry.py` → `_register_default_skills()` — import and call `register_skills()`
- `skills/outcome/__init__.py` or `skills/category/__init__.py` — add to imports

### 5. Verify
```bash
python3 -m py_compile skills/composer.py
python3 -m py_compile skills/your_new_file.py
```

## Common FFMPEG Filter Patterns

### Video filters (most common)
```python
# Simple filter
video_filters.append("hflip")

# Filter with parameters
video_filters.append(f"eq=brightness={val}")

# Chained filters (comma-separated in one string)
video_filters.append(f"crop=iw/2:ih/2,scale=1920:1080")

# Time-based expressions
video_filters.append(f"rotate={speed}*t:fillcolor=black")

# Random values
video_filters.append(f"crop=iw-20:ih-20:10+10*random(1):10+10*random(2)")
```

### Parameter access pattern
```python
# Always use .get() with defaults
value = float(params.get("amount", 1.0))
mode = params.get("mode", "normal")
enabled = bool(params.get("enabled", True))
```

## Important Conventions
- Skill names are lowercase with underscores
- Tags should include common search terms users might type
- Examples should show both default and parameterized usage
- Parameter types: INT, FLOAT, STRING, BOOL, CHOICE, TIME, COLOR
