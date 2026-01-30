"""Skill registry for managing available editing skills."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Any


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
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    choices: Optional[list[str]] = None

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
            if self.min_value is not None and value < self.min_value:
                return False, f"Parameter '{self.name}' must be >= {self.min_value}"
            if self.max_value is not None and value > self.max_value:
                return False, f"Parameter '{self.name}' must be <= {self.max_value}"

        elif self.type == ParameterType.FLOAT:
            if not isinstance(value, (int, float)):
                return False, f"Parameter '{self.name}' must be a number"
            if self.min_value is not None and value < self.min_value:
                return False, f"Parameter '{self.name}' must be >= {self.min_value}"
            if self.max_value is not None and value > self.max_value:
                return False, f"Parameter '{self.name}' must be <= {self.max_value}"

        elif self.type == ParameterType.STRING:
            if not isinstance(value, str):
                return False, f"Parameter '{self.name}' must be a string"

        elif self.type == ParameterType.BOOL:
            if not isinstance(value, bool):
                return False, f"Parameter '{self.name}' must be a boolean"

        elif self.type == ParameterType.CHOICE:
            if self.choices and value not in self.choices:
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

    def validate_params(self, params: dict) -> tuple[bool, list[str]]:
        """Validate parameters for this skill.

        Args:
            params: Dictionary of parameter values.

        Returns:
            Tuple of (is_valid, list of error messages).
        """
        errors = []
        for param in self.parameters:
            value = params.get(param.name, param.default)
            is_valid, error = param.validate(value)
            if not is_valid:
                errors.append(error)
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
        self._by_category: dict[SkillCategory, list[str]] = {
            cat: [] for cat in SkillCategory
        }
        self._by_tag: dict[str, list[str]] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill.

        Args:
            skill: Skill to register.
        """
        self._skills[skill.name] = skill
        self._by_category[skill.category].append(skill.name)

        for tag in skill.tags:
            if tag not in self._by_tag:
                self._by_tag[tag] = []
            self._by_tag[tag].append(skill.name)

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
        return [self._skills[name] for name in self._by_category.get(category, [])]

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
        results = []
        for skill in self._skills.values():
            if (
                query in skill.name.lower() or
                query in skill.description.lower() or
                any(query in tag.lower() for tag in skill.tags)
            ):
                results.append(skill)
        return results

    def to_prompt_string(self) -> str:
        """Generate a string representation for LLM prompts.

        Returns:
            Formatted string describing all skills.
        """
        lines = ["# Available Skills\n"]

        for category in SkillCategory:
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

        return "\n".join(lines)

    def to_json_schema(self) -> dict:
        """Generate JSON schema for skill invocations.

        Returns:
            JSON schema dict for validation.
        """
        skill_schemas = {}

        for name, skill in self._skills.items():
            properties = {}
            required = []

            for param in skill.parameters:
                prop = {
                    "description": param.description,
                }

                if param.type == ParameterType.INT:
                    prop["type"] = "integer"
                    if param.min_value is not None:
                        prop["minimum"] = int(param.min_value)
                    if param.max_value is not None:
                        prop["maximum"] = int(param.max_value)
                elif param.type == ParameterType.FLOAT:
                    prop["type"] = "number"
                    if param.min_value is not None:
                        prop["minimum"] = param.min_value
                    if param.max_value is not None:
                        prop["maximum"] = param.max_value
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

        return {
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
    from .outcome import cinematic, vintage, social, effects

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
