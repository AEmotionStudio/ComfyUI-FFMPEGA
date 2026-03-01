# Bolt's Journal ⚡

## 2026-02-16 - Compose Hot Path: 4 Redundant Parameter Loops
**Learning:** `SkillComposer.compose()` iterates over `skill.parameters` 4 separate times per pipeline step (default fill, type coerce, range clamp, validation/drop). Each loop does `O(M)` work where M = number of parameters. For N steps in a pipeline, this totals `4×N×M` iterations when `N×M` suffices.
**Action:** Merge all 4 parameter processing loops into a single pass. This is the compose hot path — called for every pipeline execution.

## 2026-02-16 - Skill Parameter Normalization Cache
**Learning:** `SkillComposer._normalize_params` rebuilds `param_map` and `alias_map` dictionaries on every call by iterating over `skill.parameters`. This is an O(M) operation called for every step in the pipeline.
**Action:** Move this map building logic to `Skill.__post_init__` and cache the maps in the `Skill` object. This reduces `_normalize_params` to O(1) map lookups, yielding a ~31% performance improvement in normalization benchmarks.

## 2026-02-16 - Choice Parameter Validation Optimization
**Learning:** `SkillParameter.validate` and `SkillComposer.compose` used O(N) list scans to validate and normalize `CHOICE` parameters. This was done repeatedly for every parameter in every pipeline step.
**Action:** Replaced O(N) list scans with O(1) dictionary lookups using the pre-computed `_choice_map`. This handles exact matches, case insensitivity, and underscore normalization in constant time. Benchmark showed ~100x speedup for this specific operation.

## 2026-02-23 - String Replacement Performance
**Learning:** For escaping a small set of characters (7) in short strings (paths), `str.translate` was found to be ~15x slower than multiple `if char in s: s.replace(...)` calls. The overhead of `translate` table lookup outweighs the benefit of a single pass for typical path lengths.
**Action:** Use "Check First" pattern (`if char in s: s.replace(...)`) for string sanitization instead of `str.translate` or unconditional `replace`.

## 2026-02-24 - Tensor to Video Encoding Performance
**Learning:** An attempt to optimize `frames_to_tensor` using a `uint8` intermediate buffer failed because the final `float()` cast and division (`div_(255.0)`) negated the gains. However, profiling `images_to_video` revealed that `libx264` encoding speed was the bottleneck for temp file creation.
**Action:** Switched FFMPEG preset from `fast` to `ultrafast` in `MediaConverter.images_to_video`. This yielded a **6.5x speedup** (12.5s -> 1.9s for 50 frames) for temporary video generation, which is critical for multi-input skills (concat, overlay). File size increased by ~15%, which is acceptable for transient files.

## 2026-02-28 - FFMPEG Template Rendering Optimization
**Learning:** In `SkillComposer._skill_to_filters`, replacing `{placeholder}` strings in `skill.ffmpeg_template` and `skill.pipeline` was doing unconditional `.replace()` calls for every `params` and `skill.parameters` (defaults) combination. Since skills often have many default parameters that do not exist in the actual template string, iterating over all defaults unconditionally causes significant overhead. Additionally, many pipeline steps have no placeholders at all.
**Action:** Implemented the "Check First" pattern. First, check if `"{` exists in the template. If not, skip all replacements entirely. For skill defaults, check if `f"{{{sp.name}}}"` is present before calling `.replace()`. Furthermore, if `"{` disappears from the string at any point, early break from the loop. This optimized string replacement logic yields a **~1.5x speedup** for template rendering in the composer hot path.
