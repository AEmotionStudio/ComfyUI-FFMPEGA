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

## 2026-03-05 - Zero-Friction Interactions
**Learning:** Blocking `confirm()` dialogs disrupt flow, especially for frequent actions like pasting or randomization. When a robust undo/restore mechanism (like "Restore Previous") is present, confirmation dialogs become redundant friction.
**Action:** Remove `confirm()` dialogs from destructive actions (Clear, Replace) if a "Restore" safety net exists, relying on non-blocking visual feedback (flashes) instead.

## 2026-03-10 - Status Updates for Screen Readers
**Learning:** While LiteGraph is canvas-based, custom nodes often use DOM overlays for previews and status bars. Adding `role="status"` or `aria-live="polite"` to these DOM elements bridges the gap for screen reader users during async operations (uploads, processing) where visual cues alone are insufficient.
**Action:** Ensure all dynamic text updates in DOM overlays (like info bars or copy feedback) have appropriate ARIA live region attributes to announce status changes.

## 2026-03-24 - Stable Temporary Feedback
**Learning:** When providing temporary UI feedback (like "Copied!"), rapid interactions can lead to race conditions where the restoration logic accidentally saves the feedback message as the "original" text.
**Action:** Always store the true original state in a dedicated property (e.g., `_originalText`) on the element itself, and clear any pending timeouts before applying new feedback. This ensures 100% stability regardless of click speed.

## 2026-03-25 - Invisible Focusable Overlays
**Learning:** Overlay buttons that appear on hover (opacity: 0 -> 1) are invisible to keyboard users when focused unless explicit `focus` listeners toggle their visibility.
**Action:** Always pair `mouseenter`/`mouseleave` listeners with `focus`/`blur` listeners for opacity toggling on interactive overlay elements to ensure keyboard accessibility.

## 2026-03-30 - Inline Styles and Focus States
**Learning:** Using inline styles for hover effects (via JS mouseenter/mouseleave) often leaves keyboard users behind because focus states are missed.
**Action:** When implementing inline hover styles, always implement a corresponding focus style (or use a unified state manager) to ensure keyboard users receive visual feedback.

## 2026-04-12 - Drag-and-Drop Discoverability
**Learning:** In canvas-based UIs like ComfyUI, users often don't realize that standard HTML drag-and-drop works unless the drop target visually responds *during* the drag (e.g., dashed border, text change).
**Action:** Add explicit `dragover` handlers to DOM widgets that update their style (border: dashed, background: highlight) and text ("Drop to Upload") to confirm the drop target is active.
