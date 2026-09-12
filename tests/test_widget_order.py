"""Pin the Agent node's emitted widget order.

ComfyUI restores widget values *by position*, not by name. A saved workflow
stores a flat `widgets_values` array, so if INPUT_TYPES ever emits its keys
in a different order, every existing workflow silently loads its values into
the wrong widgets — a 0.7 denoise landing in a seed field, a resolution in a
CFG. Nothing errors; the output is just wrong.

That is not hypothetical for this codebase: v2.20.0 had to splice the
removed `api_key` slot out of saved workflows for exactly this reason
(`src/nodes/agent_node.ts`).

So the order is a compatibility contract, and this test is its guard. It
compares the live INPUT_TYPES key order against a committed snapshot.

If this test fails, ask which happened:

* **A widget was added.** Append it at the end of its group, then refresh the
  snapshot. Inserting into the middle renumbers every later widget.
* **A widget was removed.** Removing it shifts everything after it. Splice
  the slot in the frontend (see the v2.20.0 `api_key` handling) before
  refreshing the snapshot.
* **The refactor reordered things.** That is the bug this test exists to
  catch. Fix the order rather than the snapshot.

Refresh with::

    python tests/test_widget_order.py --update
"""

from __future__ import annotations

import json
import pathlib

import pytest

SNAPSHOT = pathlib.Path(__file__).parent / "fixtures" / "agent_widget_order.json"


def _live_order() -> dict[str, list[str]]:
    """Return the Agent node's current INPUT_TYPES key order."""
    from nodes.agent_node import FFMPEGAgentNode

    spec = FFMPEGAgentNode.INPUT_TYPES()
    return {k: list(spec.get(k, {}).keys()) for k in ("required", "optional", "hidden")}


@pytest.fixture(scope="module")
def live() -> dict[str, list[str]]:
    pytest.importorskip("torch")  # nodes/ imports torch at module level
    return _live_order()


@pytest.fixture(scope="module")
def expected() -> dict[str, list[str]]:
    return json.loads(SNAPSHOT.read_text())


class TestWidgetOrderContract:
    def test_snapshot_exists(self):
        assert SNAPSHOT.is_file(), (
            "widget-order snapshot missing — regenerate with "
            "`python tests/test_widget_order.py --update`"
        )

    @pytest.mark.parametrize("section", ["required", "optional", "hidden"])
    def test_order_is_unchanged(self, live, expected, section):
        got, want = live[section], expected[section]

        # Report the first divergence rather than dumping 234 names.
        for i, (a, b) in enumerate(zip(got, want)):
            assert a == b, (
                f"{section} widget #{i} changed: expected {b!r}, got {a!r}. "
                f"Saved workflows restore by position, so this shifts every "
                f"later widget. See this module's docstring."
            )
        assert len(got) == len(want), (
            f"{section} widget count changed: {len(want)} -> {len(got)}. "
            f"Added: {[w for w in got if w not in want]}. "
            f"Removed: {[w for w in want if w not in got]}."
        )

    def test_no_duplicate_widget_names(self, live):
        for section, names in live.items():
            assert len(names) == len(set(names)), (
                f"duplicate widget name in {section}: "
                f"{[n for n in names if names.count(n) > 1]}"
            )


if __name__ == "__main__":
    import sys

    if "--update" in sys.argv:
        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(_live_order(), indent=2) + "\n")
        print(f"Updated {SNAPSHOT}")
    else:
        print(__doc__)
