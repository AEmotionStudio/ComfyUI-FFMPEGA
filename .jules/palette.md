# Palette's Journal

## 2024-05-22 - LiteGraph Constraints
**Learning:** This project uses LiteGraph for UI, which renders components on an HTML5 Canvas. This makes standard DOM-based accessibility (ARIA labels, screen readers) difficult or impossible for individual widgets.
**Action:** Focus on visual feedback (colors, flashes) and keyboard shortcuts where possible, rather than relying on screen reader attributes.

## 2026-02-14 - Micro-Feedback Visibility
**Learning:** Visual feedback durations (like flashes) need to be long enough (e.g., 350ms+) to be reliably perceived, especially in canvas-based UIs where other cues (ARIA live regions) are absent.
**Action:** Increase duration of visual feedback animations and use explicit text labels (e.g., "Append" vs "Replace") to clarify non-standard behaviors.
