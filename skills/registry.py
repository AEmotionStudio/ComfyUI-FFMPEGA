"""Skill registry for managing available editing skills."""

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Any, Union


class SkillCategory(str, Enum):
    """Categories of skills."""
    TEMPORAL = "temporal"
    SPATIAL = "spatial"
    VISUAL = "visual"
    AUDIO = "audio"
    ENCODING = "encoding"
    OUTCOME = "outcome"


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

        elif self.type == ParameterType.BOOL:
            if not isinstance(value, bool):
                return False, f"Parameter '{self.name}' must be a boolean"

        elif self.type == ParameterType.CHOICE:
            choices = self.choices
            if choices is not None and value not in choices:
                # Try case-insensitive match
                lower_val = str(value).lower().strip()
                match: str | None = None
                for choice in choices:
                    if choice.lower() == lower_val:
                        match = choice
                        break
                # Try prefix match
                if not match:
                    prefix_matches = [c for c in choices if c.lower().startswith(lower_val)]
                    if len(prefix_matches) == 1:
                        match = prefix_matches[0]
                # Try substring match
                if not match:
                    sub_matches = [c for c in choices if lower_val in c.lower()]
                    if len(sub_matches) == 1:
                        match = sub_matches[0]
                if match:
                    # Auto-correct to valid value — return valid with the corrected value
                    # Caller should check and update the value
                    return True, f"__autocorrect__:{self.name}={match}"
                return False, f"Parameter '{self.name}' must be one of {choices}"

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

    def __post_init__(self):
        """Pre-compute search text for faster lookups."""
        parts = [self.name, self.description] + self.tags
        self._search_text = " ".join(parts).lower()

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
        for param in self.parameters:
            if param.name == name:
                return param
        return None


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
        self._skills[skill.name] = skill
        self._by_category[skill.category].append(skill)

        for tag in skill.tags:
            if tag not in self._by_tag:
                self._by_tag[tag] = []
            self._by_tag[tag].append(skill.name)

        # Invalidate cache
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

        Args:
            query: Search query.

        Returns:
            List of matching skills.
        """
        query = query.lower()
        return [
            skill for skill in self._skills.values()
            if query in skill._search_text
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
    return _registry


def _register_default_skills(registry: SkillRegistry) -> None:
    """Register all default skills."""
    from .category import temporal, spatial, visual, audio, encoding
    from .outcome import cinematic, vintage, social, effects, creative, transitions, motion

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

