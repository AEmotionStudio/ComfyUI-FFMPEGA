# Bolt's Journal ⚡

## 2026-02-16 - Compose Hot Path: 4 Redundant Parameter Loops
**Learning:** `SkillComposer.compose()` iterates over `skill.parameters` 4 separate times per pipeline step (default fill, type coerce, range clamp, validation/drop). Each loop does `O(M)` work where M = number of parameters. For N steps in a pipeline, this totals `4×N×M` iterations when `N×M` suffices.
**Action:** Merge all 4 parameter processing loops into a single pass. This is the compose hot path — called for every pipeline execution.
