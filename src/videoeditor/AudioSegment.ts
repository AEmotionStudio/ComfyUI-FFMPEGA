/**
 * AudioSegment — data model and manager for independent audio track editing.
 *
 * Mirrors EditManager but for audio segments. Each segment carries
 * per-segment audio properties (volume, fade, EQ, mute).
 *
 * By default, audio segments are linked to video: when video splits,
 * audio splits at the same point. Users can unlink to trim independently.
 */

import { EQPreset } from './AudioMixer';

export interface AudioSegment {
    id: string;
    start: number;
    end: number;
    volume: number;          // 0–2 (0% to 200%)
    fadeIn: number;          // seconds
    fadeOut: number;         // seconds
    eq: EQPreset;
    muted: boolean;
}

let _nextAudioId = 0;
export function genAudioId(): string {
    return `aseg_${++_nextAudioId}_${Date.now()}`;
}

export class AudioEditManager {
    segments: AudioSegment[] = [];
    videoDuration: number = 0;
    linked: boolean = true;  // linked to video segments by default

    /** Initialize with a single segment spanning the full video */
    init(duration: number): void {
        this.videoDuration = duration;
        this.segments = [{
            id: genAudioId(),
            start: 0,
            end: duration,
            volume: 1.0,
            fadeIn: 0,
            fadeOut: 0,
            eq: 'flat',
            muted: false,
        }];
    }

    /** Create an audio segment with defaults, optionally overridden */
    createSegment(
        start: number,
        end: number,
        overrides?: Partial<Pick<AudioSegment, 'volume' | 'fadeIn' | 'fadeOut' | 'eq' | 'muted'>>,
    ): AudioSegment {
        return {
            id: genAudioId(),
            start,
            end,
            volume: 1.0,
            fadeIn: 0,
            fadeOut: 0,
            eq: 'flat',
            muted: false,
            ...overrides,
        };
    }

    /** Split the segment containing the given timestamp into two */
    splitAt(timestamp: number): boolean {
        const idx = this.segments.findIndex(
            s => timestamp > s.start && timestamp < s.end,
        );
        if (idx === -1) return false;

        const seg = this.segments[idx];
        const left: AudioSegment = { ...seg, id: seg.id, end: timestamp };
        const right: AudioSegment = { ...seg, id: genAudioId(), start: timestamp };

        this.segments.splice(idx, 1, left, right);
        return true;
    }

    /** Add a new segment */
    addSegment(start: number, end: number): AudioSegment {
        start = Math.max(0, start);
        end = Math.min(this.videoDuration, end);
        if (end <= start) {
            throw new Error(`Invalid audio segment: end (${end}) <= start (${start})`);
        }
        const seg = this.createSegment(start, end);
        const idx = this.segments.findIndex(s => s.start > start);
        if (idx === -1) {
            this.segments.push(seg);
        } else {
            this.segments.splice(idx, 0, seg);
        }
        return seg;
    }

    /** Remove a segment by ID */
    removeSegment(id: string): boolean {
        const idx = this.segments.findIndex(s => s.id === id);
        if (idx === -1) return false;
        this.segments.splice(idx, 1);
        return true;
    }

    /** Update a segment's time range */
    updateSegment(id: string, start: number, end: number): boolean {
        const seg = this.segments.find(s => s.id === id);
        if (!seg) return false;

        start = Math.max(0, start);
        end = Math.min(this.videoDuration, end);
        if (end <= start + 0.05) return false;

        seg.start = start;
        seg.end = end;
        return true;
    }

    /** Update audio properties of a segment */
    updateSegmentAudio(
        id: string,
        props: Partial<Pick<AudioSegment, 'volume' | 'fadeIn' | 'fadeOut' | 'eq' | 'muted'>>,
    ): boolean {
        const seg = this.segments.find(s => s.id === id);
        if (!seg) return false;
        Object.assign(seg, props);
        return true;
    }

    /** Move a segment from one position to another */
    reorderSegments(fromIdx: number, toIdx: number): boolean {
        if (fromIdx < 0 || fromIdx >= this.segments.length) return false;
        if (toIdx < 0 || toIdx >= this.segments.length) return false;
        if (fromIdx === toIdx) return false;

        const [seg] = this.segments.splice(fromIdx, 1);
        this.segments.splice(toIdx, 0, seg);
        return true;
    }

    /** Replace all segments at once (e.g. when syncing from video segments) */
    replaceAll(newSegments: AudioSegment[]): void {
        this.segments = newSegments;
    }

    /** Reset to a single full-length segment */
    reset(): void {
        this.segments = [this.createSegment(0, this.videoDuration)];
    }

    /** Get the volume at a given source time (for live preview) */
    getVolumeAtTime(time: number): number {
        for (const seg of this.segments) {
            if (time >= seg.start && time <= seg.end) {
                if (seg.muted) return 0;

                let vol = seg.volume;

                // Apply fade in
                if (seg.fadeIn > 0) {
                    const elapsed = time - seg.start;
                    if (elapsed < seg.fadeIn) {
                        vol *= elapsed / seg.fadeIn;
                    }
                }

                // Apply fade out
                if (seg.fadeOut > 0) {
                    const remaining = seg.end - time;
                    if (remaining < seg.fadeOut) {
                        vol *= remaining / seg.fadeOut;
                    }
                }

                return vol;
            }
        }
        return 0; // In a gap — mute
    }

    /** Total output duration of all segments */
    getOutputDuration(): number {
        return this.segments.reduce((sum, s) => sum + (s.end - s.start), 0);
    }

    /** Check if segments differ from a full unedited video */
    hasEdits(): boolean {
        if (this.segments.length !== 1) return true;
        const s = this.segments[0];
        return (
            Math.abs(s.start) > 0.01 ||
            Math.abs(s.end - this.videoDuration) > 0.01 ||
            Math.abs(s.volume - 1.0) > 0.01 ||
            s.fadeIn > 0 ||
            s.fadeOut > 0 ||
            s.eq !== 'flat' ||
            s.muted
        );
    }

    /** Serialize */
    toJSON(): object[] {
        return this.segments.map(s => ({
            start: s.start,
            end: s.end,
            volume: s.volume,
            fadeIn: s.fadeIn,
            fadeOut: s.fadeOut,
            eq: s.eq,
            muted: s.muted,
        }));
    }

    /** Deserialize */
    fromJSON(data: object[]): void {
        this.segments = data.map((d: any) => ({
            id: genAudioId(),
            start: d.start ?? 0,
            end: d.end ?? this.videoDuration,
            volume: d.volume ?? 1.0,
            fadeIn: d.fadeIn ?? 0,
            fadeOut: d.fadeOut ?? 0,
            eq: d.eq ?? 'flat',
            muted: d.muted ?? false,
        }));
    }
}
