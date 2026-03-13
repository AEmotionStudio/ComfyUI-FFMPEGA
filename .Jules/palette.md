## 2024-05-24 - Add Empty State for Text Overlays List
**Learning:** To improve frontend discoverability and prevent user confusion, always provide a descriptive empty state with a helpful call to action for dynamic UI lists (e.g., text overlays or items) when they are empty.
**Action:** When implementing new lists or collections in the frontend UI, explicitly check for the empty state (`length === 0`) and render a dedicated "empty state" UI component with an icon (`aria-hidden="true"`) and clear instructions for the user.
