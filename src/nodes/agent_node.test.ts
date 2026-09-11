/**
 * Loading workflows saved while the Agent node still had an `api_key`
 * widget. ComfyUI restores widgets_values by position, so the removed
 * slot has to be spliced out before the restore or every later value
 * lands on the wrong widget.
 */

import { describe, it, expect, vi } from "vitest";
import { dropRemovedApiKeyValue, registerAgentNode } from "./agent_node";
import type { AgentSerializedInfo } from "./agent_node";
import type { ComfyNodeType, ComfyNodeData } from "@ffmpega/types/comfyui";

/** The Agent's current serialized widgets around the removed slot. */
const WIDGETS = [
    "prompt", "video_path", "llm_model", "no_llm_mode", "quality_preset",
    "seed", "control_after_generate", "save_output", "output_path",
    "ollama_url", "custom_model", "use_vision", "verify_output",
];

describe("dropRemovedApiKeyValue", () => {
    it("drops api_key by name when the save has named values", () => {
        const info: AgentSerializedInfo = {
            widgets_values: ["p", "/v.mp4", "custom", "sk-secret", "qwen3:14b", true],
            widgets_values_named: {
                prompt: "p", video_path: "/v.mp4", llm_model: "custom",
                api_key: "sk-secret", custom_model: "qwen3:14b", use_vision: true,
            },
        };
        dropRemovedApiKeyValue(info, WIDGETS);
        expect(info.widgets_values).toEqual(["p", "/v.mp4", "custom", "qwen3:14b", true]);
        expect(info.widgets_values_named).not.toHaveProperty("api_key");
    });

    it("leaves a named save without api_key alone", () => {
        // Saved after the removal — already aligned, even though the slot
        // after custom_model happens to hold a string here.
        const values = ["a", "b", "c"];
        const info: AgentSerializedInfo = {
            widgets_values: [...values],
            widgets_values_named: { prompt: "a", video_path: "b", llm_model: "c" },
        };
        dropRemovedApiKeyValue(info, ["prompt", "custom_model", "video_path", "llm_model"]);
        expect(info.widgets_values).toEqual(values);
    });

    it("drops the api_key slot from a positional save", () => {
        const old = [
            "p", "/v.mp4", "custom", "manual", "standard", 0, "fixed", false, "",
            "http://localhost:11434", "sk-secret", "qwen3:14b", true, false,
        ];
        const info: AgentSerializedInfo = { widgets_values: [...old] };
        dropRemovedApiKeyValue(info, WIDGETS);
        expect(info.widgets_values).toEqual([
            "p", "/v.mp4", "custom", "manual", "standard", 0, "fixed", false, "",
            "http://localhost:11434", "qwen3:14b", true, false,
        ]);
    });

    it("leaves a positional save from the current layout alone", () => {
        const current = [
            "p", "/v.mp4", "none", "manual", "standard", 0, "fixed", false, "",
            "http://localhost:11434", "", true, false,
        ];
        const info: AgentSerializedInfo = { widgets_values: [...current] };
        dropRemovedApiKeyValue(info, WIDGETS);
        expect(info.widgets_values).toEqual(current);
    });

    it("matches today's assignments for the bundled example layout", () => {
        // example_workflows/*.json predate the current layout and are
        // already one slot out; the splice must not make them worse.
        const example = [
            "prompt", "", "gemini-cli", "standard", 0, "randomize", false, "",
            "", "", "http://localhost:11434", "", "", -1, "auto",
        ];
        const info: AgentSerializedInfo = { widgets_values: [...example] };
        dropRemovedApiKeyValue(info, WIDGETS);
        const after = info.widgets_values!;
        // Before the removal widget i got example[i] for i < 10 (ollama_url)
        // and custom_model onward got example[i + 1] once api_key sat at 10.
        expect(after.slice(0, 10)).toEqual(example.slice(0, 10));
        expect(after.slice(10)).toEqual(example.slice(11));
    });

    it("ignores info without widget values", () => {
        const info: AgentSerializedInfo = {};
        dropRemovedApiKeyValue(info, WIDGETS);
        expect(info).toEqual({});
    });
});

describe("registerAgentNode", () => {
    it("repairs widget values before the base configure restores them", () => {
        const baseConfigure = vi.fn();
        const nodeType = { prototype: { configure: baseConfigure } } as unknown as ComfyNodeType;
        registerAgentNode(nodeType, { name: "FFMPEGAgent" } as ComfyNodeData);

        const node = {
            widgets: [
                ...WIDGETS.map(name => ({ name, type: "text", value: "" })),
                { name: "preview", type: "dom", value: null, serialize: false },
            ],
        };
        const info: AgentSerializedInfo = {
            widgets_values: [
                "p", "", "none", "manual", "standard", 0, "fixed", false, "",
                "http://localhost:11434", "sk-secret", "", false, false,
            ],
        };
        (nodeType.prototype.configure as (i: AgentSerializedInfo) => void).call(node, info);

        expect(baseConfigure).toHaveBeenCalledOnce();
        const passed = baseConfigure.mock.calls[0][0] as AgentSerializedInfo;
        expect(passed.widgets_values).not.toContain("sk-secret");
        expect(passed.widgets_values![11]).toBe(false);
    });
});
