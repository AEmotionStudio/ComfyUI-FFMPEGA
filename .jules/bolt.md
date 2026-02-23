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
