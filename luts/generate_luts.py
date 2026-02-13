#!/usr/bin/env python3
"""Generate bundled .cube LUT files for FFMPEGA.

Each LUT is a 33x33x33 3D color lookup table in Adobe .cube format.
The color transformations are pure math — no licensing concerns.

Usage:
    python generate_luts.py
"""

import os
from pathlib import Path

SIZE = 33  # 33x33x33 is standard for video


def clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def write_cube(filepath: str, title: str, size: int, transform_fn):
    """Write a .cube file with the given transform function.

    transform_fn(r, g, b) -> (r, g, b) where all values are 0.0-1.0
    """
    with open(filepath, "w") as f:
        f.write(f"TITLE \"{title}\"\n")
        f.write(f"LUT_3D_SIZE {size}\n")
        f.write(f"DOMAIN_MIN 0.0 0.0 0.0\n")
        f.write(f"DOMAIN_MAX 1.0 1.0 1.0\n")
        f.write("\n")
        for bi in range(size):
            b = bi / (size - 1)
            for gi in range(size):
                g = gi / (size - 1)
                for ri in range(size):
                    r = ri / (size - 1)
                    ro, go, bo = transform_fn(r, g, b)
                    f.write(f"{clamp(ro):.6f} {clamp(go):.6f} {clamp(bo):.6f}\n")


# --- LUT transform functions ---


def cinematic_teal_orange(r, g, b):
    """Blockbuster look: teal shadows, warm orange highlights."""
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    # Push shadows toward teal, highlights toward orange
    shadow_weight = max(0, 1.0 - luma * 2.5)
    highlight_weight = max(0, luma * 2.0 - 0.8)
    mid_weight = 1.0 - shadow_weight - highlight_weight

    # Teal: slightly lower red, boost green/blue
    sr, sg, sb = r * 0.7, g * 1.05, b * 1.15
    # Orange: boost red, slightly lower blue
    hr, hg, hb = r * 1.2, g * 0.95, b * 0.7
    # Mid: slight warmth
    mr, mg, mb = r * 1.05, g * 1.0, b * 0.92

    ro = sr * shadow_weight + mr * mid_weight + hr * highlight_weight
    go = sg * shadow_weight + mg * mid_weight + hg * highlight_weight
    bo = sb * shadow_weight + mb * mid_weight + hb * highlight_weight

    # Slight contrast boost
    ro = clamp((ro - 0.5) * 1.15 + 0.5)
    go = clamp((go - 0.5) * 1.15 + 0.5)
    bo = clamp((bo - 0.5) * 1.15 + 0.5)
    return ro, go, bo


def film_noir(r, g, b):
    """High contrast desaturation with crushed blacks and blue tint."""
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    # Heavy desaturation
    r = lerp(luma, r, 0.15)
    g = lerp(luma, g, 0.15)
    b = lerp(luma, b, 0.15)
    # Crush blacks, boost contrast
    r = clamp((r - 0.08) * 1.35)
    g = clamp((g - 0.08) * 1.35)
    b = clamp((b - 0.08) * 1.35)
    # Slight cool/blue tint
    b = clamp(b + 0.03)
    return r, g, b


def warm_vintage(r, g, b):
    """Faded warm tones, lifted shadows, slight magenta in mids."""
    # Lift shadows (raise black point)
    r = lerp(0.06, r, 0.92) * 1.0
    g = lerp(0.04, g, 0.92) * 1.0
    b = lerp(0.03, b, 0.90) * 1.0
    # Warm shift
    r = clamp(r * 1.08)
    g = clamp(g * 1.02)
    b = clamp(b * 0.88)
    # Slight fade (reduce contrast)
    r = clamp((r - 0.5) * 0.85 + 0.52)
    g = clamp((g - 0.5) * 0.85 + 0.50)
    b = clamp((b - 0.5) * 0.85 + 0.48)
    # Slight magenta in mids
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    mid = max(0, 1.0 - abs(luma - 0.5) * 4)
    r = clamp(r + mid * 0.03)
    b = clamp(b + mid * 0.02)
    return r, g, b


def cool_scifi(r, g, b):
    """Cold blue/cyan shift with high contrast."""
    # Push toward blue/cyan
    r = r * 0.85
    g = g * 1.02
    b = b * 1.2
    # High contrast S-curve
    def scurve(v):
        # Simple sigmoid-like S-curve
        v = clamp(v)
        return clamp(v * v * (3.0 - 2.0 * v) * 1.1)
    r = scurve(r)
    g = scurve(g)
    b = scurve(b)
    # Desaturate slightly
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    r = lerp(luma, r, 0.8)
    g = lerp(luma, g, 0.8)
    b = lerp(luma, b, 0.8)
    return r, g, b


def golden_hour(r, g, b):
    """Warm amber glow with soft contrast."""
    # Warm cast
    r = clamp(r * 1.15)
    g = clamp(g * 1.05)
    b = clamp(b * 0.8)
    # Soft contrast (reduced)
    r = clamp((r - 0.5) * 0.9 + 0.53)
    g = clamp((g - 0.5) * 0.9 + 0.51)
    b = clamp((b - 0.5) * 0.9 + 0.47)
    # Slight glow in highlights
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    glow = max(0, luma - 0.6) * 0.3
    r = clamp(r + glow * 1.2)
    g = clamp(g + glow * 0.8)
    b = clamp(b + glow * 0.3)
    return r, g, b


def bleach_bypass(r, g, b):
    """Desaturated high-contrast, silver-retain look."""
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    # Mix original with luminance (partial desaturation)
    r = lerp(luma, r, 0.4)
    g = lerp(luma, g, 0.4)
    b = lerp(luma, b, 0.4)
    # Overlay blend with itself for contrast
    def overlay(base, blend):
        if base < 0.5:
            return 2 * base * blend
        else:
            return 1 - 2 * (1 - base) * (1 - blend)
    r = lerp(r, overlay(r, luma), 0.5)
    g = lerp(g, overlay(g, luma), 0.5)
    b = lerp(b, overlay(b, luma), 0.5)
    return clamp(r), clamp(g), clamp(b)


def cross_process(r, g, b):
    """Cross-processed look: green shadows, magenta highlights."""
    # Shift channel curves
    # Red: boost highlights
    r = clamp(r * r * 0.5 + r * 0.6)
    # Green: slight S-curve boost
    g = clamp(g * g * (3.0 - 2.0 * g) * 1.1 + 0.02)
    # Blue: crush and shift
    b = clamp(b * 0.7 + 0.05)
    # Green tint in shadows
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    shadow = max(0, 1.0 - luma * 2)
    g = clamp(g + shadow * 0.08)
    # Magenta in highlights
    highlight = max(0, luma * 2 - 1)
    r = clamp(r + highlight * 0.06)
    b = clamp(b + highlight * 0.04)
    return r, g, b


def neutral_clean(r, g, b):
    """Subtle contrast and saturation boost, no color shift."""
    # Slight contrast (mild S-curve)
    def mild_s(v):
        v = clamp(v)
        return clamp((v - 0.5) * 1.12 + 0.5)
    r = mild_s(r)
    g = mild_s(g)
    b = mild_s(b)
    # Slight saturation boost
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    r = lerp(luma, r, 1.15)
    g = lerp(luma, g, 1.15)
    b = lerp(luma, b, 1.15)
    return clamp(r), clamp(g), clamp(b)


LUTS = [
    ("cinematic_teal_orange", "Cinematic Teal & Orange", cinematic_teal_orange),
    ("film_noir", "Film Noir", film_noir),
    ("warm_vintage", "Warm Vintage", warm_vintage),
    ("cool_scifi", "Cool Sci-Fi", cool_scifi),
    ("golden_hour", "Golden Hour", golden_hour),
    ("bleach_bypass", "Bleach Bypass", bleach_bypass),
    ("cross_process", "Cross Process", cross_process),
    ("neutral_clean", "Neutral Clean", neutral_clean),
]


def main():
    script_dir = Path(__file__).resolve().parent
    for filename, title, fn in LUTS:
        path = script_dir / f"{filename}.cube"
        print(f"Generating {path.name} ({title})...", end=" ", flush=True)
        write_cube(str(path), title, SIZE, fn)
        size_kb = os.path.getsize(path) / 1024
        print(f"{size_kb:.0f} KB")

    print(f"\nGenerated {len(LUTS)} LUT files in {script_dir}")


if __name__ == "__main__":
    main()
