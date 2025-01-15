# LUT Files for FFMPEGA

This folder contains `.cube` 3D LUT (Look-Up Table) files used by the `lut_apply` skill for professional color grading.

## Bundled LUTs

| LUT | Description |
|-----|-------------|
| `cinematic_teal_orange` | Blockbuster look — teal shadows, warm orange highlights |
| `film_noir` | High-contrast desaturation with crushed blacks |
| `warm_vintage` | Faded warm tones, lifted shadows, slight magenta |
| `cool_scifi` | Cold blue/cyan shift with high contrast |
| `golden_hour` | Warm amber glow with soft contrast |
| `bleach_bypass` | Desaturated high-contrast silver-retain look |
| `cross_process` | Green shadows, magenta highlights |
| `neutral_clean` | Subtle contrast/saturation boost, no color shift |

## Adding Your Own LUTs

Drop any `.cube` or `.3dl` file into this folder. The agent will discover it automatically via the `list_luts` tool.

**Naming tips:**
- Use descriptive filenames (e.g. `kodak_portra_400.cube`)
- Avoid spaces — use underscores instead
- Standard 33×33×33 or 64×64×64 sizes work best

## Regenerating Bundled LUTs

```bash
python luts/generate_luts.py
```
