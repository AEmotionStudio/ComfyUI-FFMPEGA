# Palette's Journal

## 2024-05-22 - LiteGraph Constraints
**Learning:** This project uses LiteGraph for UI, which renders components on an HTML5 Canvas. This makes standard DOM-based accessibility (ARIA labels, screen readers) difficult or impossible for individual widgets.
**Action:** Focus on visual feedback (colors, flashes) and keyboard shortcuts where possible, rather than relying on screen reader attributes.

## 2026-02-14 - Micro-Feedback Visibility
**Learning:** Visual feedback durations (like flashes) need to be long enough (e.g., 350ms+) to be reliably perceived, especially in canvas-based UIs where other cues (ARIA live regions) are absent.
**Action:** Increase duration of visual feedback animations and use explicit text labels (e.g., "Append" vs "Replace") to clarify non-standard behaviors.

## 2026-02-15 - Context Menu Safety Nets
**Learning:** ComfyUI custom nodes often lack built-in undo/redo for widget values, leading to user frustration when they accidentally clear or replace complex prompts.
**Action:** Adding a simple "Restore Previous" buffer (`_previousPrompt`) in the node instance provides a high-value safety net with minimal code (<20 lines).

## 2026-03-01 - Non-Blocking Node Feedback
**Learning:** ComfyUI custom nodes often default to blocking `alert()` calls for errors due to lack of standard UI. Using `flashNode` combined with DOM widget text updates provides integrated, non-blocking feedback.
**Action:** Replace `alert()` with `flashNode()` (red for errors) and update an info/status label on the node to communicate the specific error message.
