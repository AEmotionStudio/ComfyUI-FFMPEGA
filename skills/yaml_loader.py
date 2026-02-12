"""YAML-based custom skill loader.

Loads user-defined skills from YAML files and skill packs in the
``custom_skills/`` directory.  Skills can be individual ``.yaml`` files
or grouped into *skill packs* — subdirectories with their own skills
and optional Python handlers for complex filter logic.

Directory layout::

    custom_skills/
    ├── my_skill.yaml              # Individual YAML skill
    ├── retro-pack/                # Skill pack (e.g. a cloned git repo)
    │   ├── pack.yaml              # Pack metadata (optional)
    │   ├── skills/
    │   │   ├── vhs_pro.yaml
    │   │   └── betamax.yaml
    │   └── handlers.py            # Optional Python handlers
    └── examples/                  # Shipped reference examples
        ├── warm_glow.yaml
        └── film_burn.yaml
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from .registry import (
    Skill,
    SkillCategory,
    SkillParameter,
    SkillRegistry,
    ParameterType,
)

logger = logging.getLogger("ffmpega")

# ------------------------------------------------------------------ #
#   YAML → Skill conversion                                          #
# ------------------------------------------------------------------ #

# Map YAML category strings to SkillCategory enum values.
_CATEGORY_MAP: dict[str, SkillCategory] = {
    "temporal": SkillCategory.TEMPORAL,
    "spatial": SkillCategory.SPATIAL,
    "visual": SkillCategory.VISUAL,
    "audio": SkillCategory.AUDIO,
    "encoding": SkillCategory.ENCODING,
    "outcome": SkillCategory.OUTCOME,
    # Everything else falls under CUSTOM (added below).
}

# Map YAML type strings to ParameterType enum values.
_TYPE_MAP: dict[str, ParameterType] = {
    "int": ParameterType.INT,
    "integer": ParameterType.INT,
    "float": ParameterType.FLOAT,
    "number": ParameterType.FLOAT,
    "string": ParameterType.STRING,
    "str": ParameterType.STRING,
    "bool": ParameterType.BOOL,
    "boolean": ParameterType.BOOL,
    "choice": ParameterType.CHOICE,
    "time": ParameterType.TIME,
    "color": ParameterType.COLOR,
}


def _parse_parameter(name: str, data: dict[str, Any]) -> SkillParameter:
    """Convert a YAML parameter dict into a ``SkillParameter``."""
    ptype = _TYPE_MAP.get(str(data.get("type", "string")).lower(), ParameterType.STRING)
    return SkillParameter(
        name=name,
        type=ptype,
        description=str(data.get("description", "")),
        required=bool(data.get("required", False)),
        default=data.get("default"),
        min_value=data.get("min"),
        max_value=data.get("max"),
        choices=data.get("choices"),
    )


def load_skill_from_yaml(path: Path) -> Optional[Skill]:
    """Parse a single YAML file into a :class:`Skill`.

    Returns ``None`` if the file is invalid or missing required fields.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:
        logger.warning("Failed to read YAML skill %s: %s", path, exc)
        return None

    if not isinstance(data, dict):
        logger.warning("Invalid YAML skill %s: top-level must be a mapping", path)
        return None

    name = data.get("name")
    if not name:
        logger.warning("Skipping YAML skill %s: missing 'name'", path)
        return None

    description = data.get("description", "")
    cat_str = str(data.get("category", "custom")).lower()
    category = _CATEGORY_MAP.get(cat_str, SkillCategory.CUSTOM)

    # Parameters
    params_raw = data.get("parameters", {})
    parameters: list[SkillParameter] = []
    if isinstance(params_raw, dict):
        for pname, pdata in params_raw.items():
            if isinstance(pdata, dict):
                parameters.append(_parse_parameter(pname, pdata))

    # Template / pipeline
    ffmpeg_template = data.get("ffmpeg_template")
    pipeline = data.get("pipeline")

    # Metadata
    examples = data.get("examples", [])
    if not isinstance(examples, list):
        examples = [str(examples)]
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = [str(tags)]
    aliases = data.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = [str(aliases)]

    skill = Skill(
        name=str(name),
        category=category,
        description=str(description),
        parameters=parameters,
        ffmpeg_template=ffmpeg_template,
        pipeline=pipeline,
        examples=examples,
        tags=tags,
    )

    # Stash aliases for the registry to register later.
    skill._yaml_aliases = aliases  # type: ignore[attr-defined]
    return skill


# ------------------------------------------------------------------ #
#   Skill pack Python handler loading                                 #
# ------------------------------------------------------------------ #

def _load_handlers_module(handlers_path: Path) -> dict[str, Callable]:
    """Import a ``handlers.py`` and return a name→function mapping."""
    handlers: dict[str, Callable] = {}
    if not handlers_path.is_file():
        return handlers
    try:
        spec = importlib.util.spec_from_file_location(
            f"ffmpega_custom_handlers.{handlers_path.parent.name}",
            handlers_path,
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            for attr_name in dir(mod):
                if attr_name.startswith("_"):
                    continue
                attr = getattr(mod, attr_name)
                if callable(attr):
                    handlers[attr_name] = attr
    except Exception as exc:
        logger.warning("Failed to load handlers from %s: %s", handlers_path, exc)
    return handlers


# ------------------------------------------------------------------ #
#   Directory scanning                                                #
# ------------------------------------------------------------------ #

def load_skill_pack(
    pack_dir: Path,
    registry: SkillRegistry,
    custom_handlers: dict[str, Callable],
) -> int:
    """Load a skill pack from a subdirectory.

    A skill pack has the structure::

        pack_dir/
        ├── pack.yaml        # optional metadata
        ├── skills/          # YAML skill definitions
        │   └── *.yaml
        └── handlers.py      # optional Python handlers

    If a ``skills/`` subdirectory exists, YAML files are loaded from
    there.  Otherwise, YAML files in the pack root are loaded.

    Returns the number of skills successfully loaded.
    """
    loaded = 0

    # Load optional Python handlers first
    handlers_path = pack_dir / "handlers.py"
    pack_handlers = _load_handlers_module(handlers_path)
    custom_handlers.update(pack_handlers)

    # Find YAML skill files
    skills_dir = pack_dir / "skills"
    if skills_dir.is_dir():
        yaml_files = sorted(skills_dir.glob("*.yaml")) + sorted(skills_dir.glob("*.yml"))
    else:
        yaml_files = sorted(pack_dir.glob("*.yaml")) + sorted(pack_dir.glob("*.yml"))
        # Exclude pack.yaml itself
        yaml_files = [f for f in yaml_files if f.name != "pack.yaml"]

    for yf in yaml_files:
        skill = load_skill_from_yaml(yf)
        if skill:
            registry.register(skill)
            # Register aliases
            aliases = getattr(skill, "_yaml_aliases", [])
            for alias in aliases:
                registry.register_alias(alias, skill.name)
            loaded += 1
            logger.info("Loaded custom skill '%s' from %s", skill.name, yf)

    return loaded


def load_custom_skills(
    registry: SkillRegistry,
    custom_handlers: dict[str, Callable],
) -> int:
    """Scan the ``custom_skills/`` directory and register all found skills.

    Handles both individual YAML files at the top level and skill pack
    subdirectories.  Returns the total number of skills loaded.

    Args:
        registry: The skill registry to register skills into.
        custom_handlers: Dict to populate with Python handler functions
            from skill packs.  Keys are skill names, values are callables.
    """
    # custom_skills/ is at the project root, next to skills/
    project_root = Path(__file__).resolve().parent.parent
    custom_dir = project_root / "custom_skills"

    if not custom_dir.is_dir():
        return 0

    total = 0

    # 1. Load individual YAML files at the top level
    for yf in sorted(custom_dir.glob("*.yaml")) + sorted(custom_dir.glob("*.yml")):
        skill = load_skill_from_yaml(yf)
        if skill:
            registry.register(skill)
            aliases = getattr(skill, "_yaml_aliases", [])
            for alias in aliases:
                registry.register_alias(alias, skill.name)
            total += 1
            logger.info("Loaded custom skill '%s' from %s", skill.name, yf)

    # 2. Load skill packs (subdirectories)
    for entry in sorted(custom_dir.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            # Skip the examples directory shipped with the project
            if entry.name == "examples":
                # Still load examples as custom skills
                pass
            total += load_skill_pack(entry, registry, custom_handlers)

    if total > 0:
        logger.info("Loaded %d custom skill(s) from %s", total, custom_dir)

    return total
