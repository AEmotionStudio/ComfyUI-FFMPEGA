
import os
import sys
from unittest.mock import MagicMock
import time

import pytest

# Save any real modules so we can restore them after this file's tests run.
_MOCKED_MODULES = ("skills.composer", "folder_paths")
_saved = {m: sys.modules.get(m) for m in _MOCKED_MODULES}

for _m in _MOCKED_MODULES:
    if _m not in sys.modules:
        sys.modules[_m] = MagicMock()

# Now we can import
try:
    from skills.registry import SkillRegistry, Skill, SkillCategory
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from skills.registry import SkillRegistry, Skill, SkillCategory


@pytest.fixture(autouse=True, scope="module")
def _restore_mocked_modules():
    """Restore any real modules that were replaced by our test-time mocks."""
    yield
    for m, original in _saved.items():
        if original is None:
            sys.modules.pop(m, None)
        else:
            sys.modules[m] = original


def test_skill_registry_caching():
    """Verify that SkillRegistry uses caching and invalidates it correctly."""
    registry = SkillRegistry()

    # 1. Initial empty registry
    prompt1 = registry.to_prompt_string()
    schema1 = registry.to_json_schema()

    assert registry._cached_prompt_string is not None
    assert registry._cached_json_schema is not None
    assert prompt1 == registry._cached_prompt_string
    assert schema1 == registry._cached_json_schema

    # 2. Register a new skill
    skill = Skill(
        name="test_skill",
        category=SkillCategory.TEMPORAL,  # Ensure this category exists or is mocked
        description="A test skill",
    )
    registry.register(skill)

    # 3. Verify cache invalidation
    assert registry._cached_prompt_string is None
    assert registry._cached_json_schema is None

    # 4. Regenerate and verify new content
    prompt2 = registry.to_prompt_string()
    schema2 = registry.to_json_schema()

    assert registry._cached_prompt_string is not None
    assert registry._cached_json_schema is not None
    assert "test_skill" in prompt2
    assert "test_skill" in str(schema2)
    assert prompt2 != prompt1

def test_skill_registry_performance_benchmark():
    """Benchmark to prompt string generation performance."""
    registry = SkillRegistry()

    # Populate with dummy skills to make the prompt generation somewhat heavy
    for i in range(100):
        skill = Skill(
            name=f"skill_{i}",
            category=SkillCategory.TEMPORAL,
            description=f"Description for skill {i}",
            examples=[f"Example {j}" for j in range(5)]
        )
        registry.register(skill)

    # Measure time for first call (cold cache)
    start_time = time.time()
    registry.to_prompt_string()
    cold_time = time.time() - start_time

    # Measure time for subsequent calls (warm cache)
    iterations = 1000
    start_time = time.time()
    for _ in range(iterations):
        registry.to_prompt_string()
    warm_total_time = time.time() - start_time
    warm_avg_time = warm_total_time / iterations

    print(f"Cold time: {cold_time:.6f}s")
    print(f"Warm avg time: {warm_avg_time:.9f}s")

    assert warm_avg_time < 0.0001, "Cached access should be faster than 0.1ms"
    if cold_time > 0.001:
        speedup = cold_time / warm_avg_time
        print(f"Speedup: {speedup:.2f}x")
        assert speedup > 10, "Caching should provide at least 10x speedup"

if __name__ == "__main__":
    try:
        test_skill_registry_caching()
        print("test_skill_registry_caching passed")
        test_skill_registry_performance_benchmark()
        print("test_skill_registry_performance_benchmark passed")
    except AssertionError as e:
        print(f"Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
