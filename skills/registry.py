"""Skill registry for managing available editing skills."""

import copy
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Any, Union

logger = logging.getLogger("ffmpega")


class SkillCategory(str, Enum):
    """Categories of skills."""
    TEMPORAL = "temporal"
    SPATIAL = "spatial"
    VISUAL = "visual"
    AUDIO = "audio"
    ENCODING = "encoding"
    OUTCOME = "outcome"
    CUSTOM = "custom"


class ParameterType(str, Enum):
    """Types of skill parameters."""
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BOOL = "bool"
    CHOICE = "choice"
    TIME = "time"
    COLOR = "color"


@dataclass
class SkillParameter:
    """Definition of a skill parameter."""
    name: str
    type: ParameterType
    description: str
    required: bool = True
    default: Any = None
    min_value: float | None = None
    max_value: float | None = None
    choices: list[str] | None = None
    aliases: list[str] | None = None
    _choice_map: dict[str, str] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self):
        """Pre-compute choice map for faster validation."""
        if self.type == ParameterType.CHOICE and self.choices:
            for c in self.choices:
                # Exact match
                self._choice_map[c] = c
                # Lowercase match
                self._choice_map[c.lower()] = c
                # Underscore -> hyphen normalization (e.g. bottom_right -> bottom-right)
                normalized = c.replace("-", "_")
                if normalized != c:
                    self._choice_map[normalized] = c
                    self._choice_map[normalized.lower()] = c

    def validate(self, value: Any) -> tuple[bool, Optional[str]]:
        """Validate a parameter value.

        Args:
            value: Value to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        if value is None:
            if self.required and self.default is None:
                return False, f"Parameter '{self.name}' is required"
            return True, None

        if self.type == ParameterType.INT:
            if not isinstance(value, int):
                return False, f"Parameter '{self.name}' must be an integer"
            min_val = self.min_value
            max_val = self.max_value
            if min_val is not None and value < min_val:
                return False, f"Parameter '{self.name}' must be >= {min_val}"
            if max_val is not None and value > max_val:
                return False, f"Parameter '{self.name}' must be <= {max_val}"

        elif self.type == ParameterType.FLOAT:
            if not isinstance(value, (int, float)):
                return False, f"Parameter '{self.name}' must be a number"
            min_val = self.min_value
            max_val = self.max_value
            if min_val is not None and value < min_val:
                return False, f"Parameter '{self.name}' must be >= {min_val}"
            if max_val is not None and value > max_val:
                return False, f"Parameter '{self.name}' must be <= {max_val}"

        elif self.type == ParameterType.STRING:
            if not isinstance(value, str):
                return False, f"Parameter '{self.name}' must be a string"
            min_val = self.min_value
            max_val = self.max_value
            if min_val is not None and len(value) < min_val:
                return False, f"Parameter '{self.name}' must be at least {int(min_val)} characters"
            if max_val is not None and len(value) > max_val:
                return False, f"Parameter '{self.name}' must be at most {int(max_val)} characters"

        elif self.type == ParameterType.BOOL:
            if not isinstance(value, bool):
                return False, f"Parameter '{self.name}' must be a boolean"

        elif self.type == ParameterType.COLOR:
            import re
            if not isinstance(value, str):
                return False, f"Parameter '{self.name}' must be a color string"
            if not re.match(r"^#[0-9A-Fa-f]{6}$", value):
                return False, f"Parameter '{self.name}' must be a hex color like #RRGGBB"

        elif self.type == ParameterType.CHOICE:
            if self.choices:
                # ⚡ Perf: Use O(1) map lookup instead of O(N) list search.
                # _choice_map contains exact matches, lowercase, and normalized variants.
                val_str = str(value)
                if val_str in self._choice_map:
                    match = self._choice_map[val_str]
                    if match == value:
                        return True, None
                    return True, f"__autocorrect__:{self.name}={match}"

                lower_val = val_str.lower().strip()
                if lower_val in self._choice_map:
                    match = self._choice_map[lower_val]
                    return True, f"__autocorrect__:{self.name}={match}"

                # Fallback to slow prefix/substring match (O(N))
                match: str | None = None
                prefix_matches = [c for c in self.choices if c.lower().startswith(lower_val)]
                if len(prefix_matches) == 1:
                    match = prefix_matches[0]

                if not match:
                    sub_matches = [c for c in self.choices if lower_val in c.lower()]
                    if len(sub_matches) == 1:
                        match = sub_matches[0]

                if match:
                    return True, f"__autocorrect__:{self.name}={match}"
                return False, f"Parameter '{self.name}' must be one of {self.choices}"

        return True, None


@dataclass
class Skill:
    """Definition of an editing skill."""
    name: str
    category: SkillCategory
    description: str
    parameters: list[SkillParameter] = field(default_factory=list)
    ffmpeg_template: Optional[str] = None
    pipeline: Optional[list[str]] = None
    examples: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    _search_text: str = field(init=False, repr=False, default="")
    _param_map: dict[str, SkillParameter] = field(init=False, repr=False, default_factory=dict)
    _alias_map: dict[str, str] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self):
        """Pre-compute search text and parameter maps for faster lookups."""
        # Ensure tags is a list even if initialized with None
        tags = self.tags if self.tags is not None else []
        parts = [str(self.name), str(self.description)] + tags
        self._search_text = " ".join(parts).lower()

        # Build parameter maps
        self._param_map = {}
        self._alias_map = {}
        for p in self.parameters:
            self._param_map[p.name] = p
            if p.aliases:
                for alias in p.aliases:
                    self._alias_map[alias] = p.name

    def validate_params(self, params: dict) -> tuple[bool, list[str]]:
        """Validate parameters for this skill.

        Args:
            params: Dictionary of parameter values.

        Returns:
            Tuple of (is_valid, list of error messages).
        """
        errors: list[str] = []
        for param in self.parameters:
            value = params.get(param.name, param.default)
            is_valid, error = param.validate(value)
            if not is_valid and error is not None:
                errors.append(error)
            elif error and isinstance(error, str) and error.startswith("__autocorrect__:"):
                # Apply auto-corrected value back to params
                correction = error.split(":", 1)[1]
                name, corrected_value = correction.split("=", 1)
                params[name] = corrected_value
        return len(errors) == 0, errors

    def get_param(self, name: str) -> Optional[SkillParameter]:
        """Get a parameter definition by name."""
        return self._param_map.get(name)


class SkillRegistry:
    """Central registry for all available skills."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._by_category: dict[SkillCategory, list[Skill]] = {
            cat: [] for cat in SkillCategory
        }
        self._by_tag: dict[str, list[str]] = {}
        self._cached_prompt_string: Optional[str] = None
        self._cached_json_schema: Optional[dict] = None

    def register(self, skill: Skill) -> None:
        """Register a skill.

        Args:
            skill: Skill to register.
        """
        if skill.name in self._skills:
            old = self._skills[skill.name]
            cat_list = self._by_category[old.category]
            cat_list[:] = [s for s in cat_list if s.name != skill.name]
            # Remove old tag associations
            for old_tag in old.tags:
                if old_tag in self._by_tag:
                    self._by_tag[old_tag] = [
                        n for n in self._by_tag[old_tag] if n != skill.name
                    ]
        self._skills[skill.name] = skill
        self._by_category[skill.category].append(skill)

        for tag in skill.tags:
            if tag not in self._by_tag:
                self._by_tag[tag] = []
            self._by_tag[tag].append(skill.name)

        # Invalidate cache
        self._cached_prompt_string = None
        self._cached_json_schema = None

    def register_alias(self, alias: str, target_name: str) -> None:
        """Register an alias that maps to an existing skill.

        Args:
            alias: The alias name.
            target_name: The name of the existing skill to alias.
        """
        import copy
        skill = self._skills.get(target_name)
        if skill is None:
            return
        alias_skill = copy.copy(skill)
        alias_skill.name = alias
        alias_skill._search_text = " ".join(
            [alias, skill.description] + (skill.tags or [])
        ).lower()
        self._skills[alias] = alias_skill
        self._by_category[alias_skill.category].append(alias_skill)
        for tag in alias_skill.tags:
            if tag not in self._by_tag:
                self._by_tag[tag] = []
            self._by_tag[tag].append(alias)
        self._cached_prompt_string = None
        self._cached_json_schema = None

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name.

        Args:
            name: Skill name.

        Returns:
            Skill if found, None otherwise.
        """
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        """List all registered skills.

        Returns:
            List of all skills.
        """
        return list(self._skills.values())

    def list_by_category(self, category: SkillCategory) -> list[Skill]:
        """List skills in a category.

        Args:
            category: Category to filter by.

        Returns:
            List of skills in the category.
        """
        return list(self._by_category.get(category, []))

    def list_by_tag(self, tag: str) -> list[Skill]:
        """List skills with a specific tag.

        Args:
            tag: Tag to filter by.

        Returns:
            List of skills with the tag.
        """
        return [self._skills[name] for name in self._by_tag.get(tag, [])]

    def search(self, query: str) -> list[Skill]:
        """Search for skills by name or description.

        Splits the query into words and returns skills whose search text
        contains ANY of the words (OR matching).  This ensures multi-word
        queries like "color grade vignette fade" return relevant results
        instead of requiring the exact substring.

        Args:
            query: Search query (single or multi-word).

        Returns:
            List of matching skills.
        """
        words = query.lower().split()
        if not words:
            return []
        return [
            skill for skill in self._skills.values()
            if any(w in skill._search_text for w in words)
        ]

    def to_prompt_string(self) -> str:
        """Generate a string representation for LLM prompts.

        Returns:
            Formatted string describing all skills.
        """
        if self._cached_prompt_string is not None:
            return self._cached_prompt_string

        lines = ["# Available Skills\n"]

        for category in list(SkillCategory):
            skills = self.list_by_category(category)
            if not skills:
                continue

            lines.append(f"\n## {category.value.title()}\n")

            for skill in skills:
                lines.append(f"### {skill.name}")
                lines.append(f"{skill.description}\n")

                if skill.parameters:
                    lines.append("Parameters:")
                    for param in skill.parameters:
                        req = "required" if param.required else f"optional, default={param.default}"
                        lines.append(f"  - {param.name} ({param.type.value}): {param.description} [{req}]")

                if skill.examples:
                    lines.append("Examples:")
                    for ex in skill.examples:
                        lines.append(f"  - {ex}")

                lines.append("")

        self._cached_prompt_string = "\n".join(lines)
        return self._cached_prompt_string

    def to_json_schema(self) -> dict:
        """Generate JSON schema for skill invocations.

        Returns:
            JSON schema dict for validation.
        """
        if self._cached_json_schema is not None:
            return copy.deepcopy(self._cached_json_schema)

        skill_schemas = {}

        for name, skill in self._skills.items():
            properties = {}
            required = []

            for param in skill.parameters:
                prop: dict[str, Any] = {
                    "description": param.description,
                }

                if param.type == ParameterType.INT:
                    prop["type"] = "integer"
                    min_v = param.min_value
                    max_v = param.max_value
                    if min_v is not None:
                        prop["minimum"] = int(min_v)
                    if max_v is not None:
                        prop["maximum"] = int(max_v)
                elif param.type == ParameterType.FLOAT:
                    prop["type"] = "number"
                    min_v = param.min_value
                    max_v = param.max_value
                    if min_v is not None:
                        prop["minimum"] = min_v
                    if max_v is not None:
                        prop["maximum"] = max_v
                elif param.type == ParameterType.STRING:
                    prop["type"] = "string"
                elif param.type == ParameterType.BOOL:
                    prop["type"] = "boolean"
                elif param.type == ParameterType.CHOICE:
                    prop["type"] = "string"
                    if param.choices:
                        prop["enum"] = param.choices
                elif param.type == ParameterType.TIME:
                    prop["type"] = "number"
                    prop["description"] += " (seconds)"
                elif param.type == ParameterType.COLOR:
                    prop["type"] = "string"
                    prop["pattern"] = "^#[0-9A-Fa-f]{6}$"

                if param.default is not None:
                    prop["default"] = param.default

                properties[param.name] = prop

                if param.required:
                    required.append(param.name)

            skill_schemas[name] = {
                "type": "object",
                "description": skill.description,
                "properties": properties,
                "required": required,
            }

        self._cached_json_schema = {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "enum": list(self._skills.keys()),
                },
                "params": {
                    "oneOf": [
                        {"$ref": f"#/definitions/{name}"}
                        for name in skill_schemas.keys()
                    ]
                }
            },
            "definitions": skill_schemas,
            "required": ["skill", "params"],
        }
        return copy.deepcopy(self._cached_json_schema)

    # ------------------------------------------------------------------ #
    #  Hot-reload                                                          #
    # ------------------------------------------------------------------ #

    def reload(self) -> int:
        """Re-read and re-register all default and custom skills.

        Clears all internal state (skills, category/tag indexes, caches)
        and re-runs the full registration sequence, including reloading
        any YAML custom skills from ``custom_skills/``.  This lets
        ComfyUI pick up skill changes without a server restart.

        Returns:
            The number of skills registered after the reload.
        """
        logger.info("SkillRegistry: reloading all skills…")

        # Clear all internal state
        self._skills.clear()
        for cat_list in self._by_category.values():
            cat_list.clear()
        self._by_tag.clear()
        self._cached_prompt_string = None
        self._cached_json_schema = None

        # Re-register defaults
        _register_default_skills(self)

        # Re-load YAML custom skills
        try:
            from .yaml_loader import load_custom_skills  # type: ignore[import-not-found]
            self._custom_handlers = {}  # type: ignore[attr-defined]
            load_custom_skills(self, self._custom_handlers)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("SkillRegistry reload: failed to load custom skills: %s", exc)

        count = len(self._skills)
        logger.info("SkillRegistry: reload complete — %d skills registered", count)
        return count

    # ------------------------------------------------------------------ #
    #  File-watcher (optional, opt-in)                                     #
    # ------------------------------------------------------------------ #

    def start_watching(
        self,
        watch_dir: Optional[str] = None,
        interval: float = 5.0,
    ) -> None:
        """Start a background thread that polls YAML files for changes.

        When any ``.yaml`` or ``.yml`` file in *watch_dir* is modified
        (detected via mtime), :meth:`reload` is called automatically.

        This is opt-in and *disabled by default*.  Call :meth:`stop_watching`
        to clean up the background thread before shutdown.

        Args:
            watch_dir: Directory to watch.  Defaults to the
                ``custom_skills/`` sibling directory next to this file.
            interval: Poll interval in seconds (default 5.0).
        """
        import os
        import threading
        from pathlib import Path

        if getattr(self, "_watcher_timer", None) is not None:
            logger.debug("SkillRegistry: file-watcher already running")
            return

        if watch_dir is None:
            watch_dir = str(Path(__file__).resolve().parent / "custom_skills")

        watch_path = Path(watch_dir)

        # Snapshot current mtimes
        def _snapshot() -> dict[str, float]:
            if not watch_path.exists():
                return {}
            return {
                str(p): p.stat().st_mtime
                for p in watch_path.rglob("*.yaml")
            } | {
                str(p): p.stat().st_mtime
                for p in watch_path.rglob("*.yml")
            }

        self._watcher_mtimes: dict[str, float] = _snapshot()  # type: ignore[attr-defined]
        self._watcher_stop: threading.Event = threading.Event()  # type: ignore[attr-defined]

        def _poll():
            if self._watcher_stop.is_set():  # type: ignore[attr-defined]
                return
            current = _snapshot()
            if current != self._watcher_mtimes:  # type: ignore[attr-defined]
                logger.info(
                    "SkillRegistry: detected YAML changes in %s — reloading",
                    watch_dir,
                )
                self._watcher_mtimes = current  # type: ignore[attr-defined]
                try:
                    self.reload()
                except Exception as exc:
                    logger.error("SkillRegistry: reload failed: %s", exc)
            # Re-check the stop event after the potentially slow reload so that
            # a stop_watching() call that arrived while we were reloading won't
            # accidentally reschedule the timer.
            if self._watcher_stop.is_set():  # type: ignore[attr-defined]
                return
            t = threading.Timer(interval, _poll)
            t.daemon = True
            self._watcher_timer = t  # type: ignore[attr-defined]
            t.start()

        # Kick off the first poll
        t = threading.Timer(interval, _poll)
        t.daemon = True
        self._watcher_timer = t  # type: ignore[attr-defined]
        t.start()
        logger.info(
            "SkillRegistry: watching %s every %.1fs", watch_dir, interval
        )

    def stop_watching(self) -> None:
        """Stop the background file-watcher if running."""
        stop_event = getattr(self, "_watcher_stop", None)
        if stop_event is not None:
            stop_event.set()
        timer = getattr(self, "_watcher_timer", None)
        if timer is not None:
            timer.cancel()
            self._watcher_timer = None  # type: ignore[attr-defined]
        logger.debug("SkillRegistry: file-watcher stopped")


# Global registry instance
_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    """Get the global skill registry.

    Returns:
        Global SkillRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _register_default_skills(_registry)
        # Load user-defined custom skills from custom_skills/
        try:
            from .yaml_loader import load_custom_skills
            _registry._custom_handlers = {}  # type: ignore[attr-defined]
            load_custom_skills(_registry, _registry._custom_handlers)  # type: ignore[attr-defined]
        except Exception as exc:
            import logging
            logging.getLogger("ffmpega").warning(
                "Failed to load custom skills: %s", exc
            )
    return _registry


def _register_default_skills(registry: SkillRegistry) -> None:
    """Register all default skills."""
    from .category import temporal, spatial, visual, audio, encoding
    from .outcome import cinematic, vintage, social, effects, creative, transitions, motion, delivery

    # Register category skills
    temporal.register_skills(registry)
    spatial.register_skills(registry)
    visual.register_skills(registry)
    audio.register_skills(registry)
    encoding.register_skills(registry)

    # Register outcome skills
    cinematic.register_skills(registry)
    vintage.register_skills(registry)
    social.register_skills(registry)
    effects.register_skills(registry)
    creative.register_skills(registry)
    transitions.register_skills(registry)
    motion.register_skills(registry)
    delivery.register_skills(registry)
