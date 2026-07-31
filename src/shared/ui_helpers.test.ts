/**
 * Playback range maths behind the Load Video preview.
 *
 * These two decide which frame the info bar names and where playback loops
 * back, and both have to reason about `select_every_nth` — where the count of
 * selected frames and the span of source time they cover come apart.
 */

import { describe, it, expect } from "vitest";
import { frameAtTime, rangeEndSeconds } from "./ui_helpers";

describe("frameAtTime", () => {
    it("numbers frames from 1 at the in-point", () => {
        expect(frameAtTime(0, 30, 1, 120)).toBe(1);
    });

    it("advances one frame per frame period", () => {
        expect(frameAtTime(1 / 30, 30, 1, 120)).toBe(2);
        expect(frameAtTime(1.0, 30, 1, 120)).toBe(31);
    });

    it("never runs past the selected count", () => {
        // Playback can sit beyond the out-point — the clamp no longer drags it
        // back — so the readout has to hold at the last frame rather than
        // counting into a frame that was never selected.
        expect(frameAtTime(10, 30, 1, 120)).toBe(120);
    });

    it("counts selected frames, not source frames, when skipping", () => {
        // Every 2nd frame: two source frames pass per selected one.
        expect(frameAtTime(0, 30, 2, 60)).toBe(1);
        expect(frameAtTime(1 / 30, 30, 2, 60)).toBe(1);
        expect(frameAtTime(2 / 30, 30, 2, 60)).toBe(2);
        expect(frameAtTime(1.0, 30, 2, 60)).toBe(16);
    });

    it("treats a negative elapsed as the in-point", () => {
        // Scrubbing before skip_first_frames puts the playhead behind the
        // range's start; frame 0 does not exist.
        expect(frameAtTime(-2, 30, 1, 120)).toBe(1);
    });

    it("returns 0 when it cannot place a frame", () => {
        expect(frameAtTime(1, 0, 1, 120)).toBe(0);
        expect(frameAtTime(1, 30, 1, 0)).toBe(0);
    });
});

describe("rangeEndSeconds", () => {
    it("ends after the selected frames have played", () => {
        expect(rangeEndSeconds(0, 81, 1, 27)).toBeCloseTo(3.0);
    });

    it("offsets by the in-point", () => {
        expect(rangeEndSeconds(1.0, 81, 1, 27)).toBeCloseTo(4.0);
    });

    it("stretches over the source frames that skipping spans", () => {
        // 60 frames taken every 2nd are spread across 120 source frames, so the
        // range is twice as long as the selected count alone would suggest —
        // using that count directly cut playback off halfway.
        expect(rangeEndSeconds(0, 60, 2, 30)).toBeCloseTo(4.0);
        expect(rangeEndSeconds(0, 60, 1, 30)).toBeCloseTo(2.0);
    });

    it("has no end to enforce without a rate or a budget", () => {
        expect(rangeEndSeconds(0, 81, 1, 0)).toBe(Infinity);
        expect(rangeEndSeconds(0, 0, 1, 30)).toBe(Infinity);
    });
});
