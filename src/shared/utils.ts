/**
 * Shared utility functions for LoadLast modules.
 */

import type { VideoEntry } from '@ffmpega/types/loadlast';

/**
 * Capture a single frame from a video at a given time.
 * @param video - The HTMLVideoElement to capture from
 * @param time - The time in seconds to seek to
 * @returns An OffscreenCanvas with the drawn frame
 */
export function captureFrame(video: HTMLVideoElement, time: number): Promise<OffscreenCanvas> {
    return new Promise((resolve) => {
        video.currentTime = time;
        const handler = () => {
            video.removeEventListener('seeked', handler);
            const oc = new OffscreenCanvas(video.videoWidth, video.videoHeight);
            const ctx = oc.getContext('2d')!;
            ctx.drawImage(video, 0, 0);
            resolve(oc);
        };
        video.addEventListener('seeked', handler);
    });
}

/**
 * Capture multiple evenly-spaced frames from a video.
 * @param video - The HTMLVideoElement to capture from
 * @param count - Number of frames to capture
 * @returns Array of OffscreenCanvas frames
 */
export async function captureFrames(video: HTMLVideoElement, count: number): Promise<OffscreenCanvas[]> {
    const dur = video.duration;
    if (!dur || !isFinite(dur) || dur <= 0) return [];
    const results: OffscreenCanvas[] = [];
    for (let i = 0; i < count; i++) {
        const t = (dur * i) / Math.max(count - 1, 1);
        results.push(await captureFrame(video, t));
    }
    return results;
}

/**
 * Build a /view URL for a video entry.
 * @param entry - The video entry with filename, subfolder, and type
 * @returns The URL string
 */
export function viewUrl(entry: VideoEntry): string {
    const params = new URLSearchParams({
        filename: entry.filename,
        subfolder: entry.subfolder || '',
        type: entry.type || 'output',
    });
    return `/view?${params.toString()}`;
}

/**
 * Format a duration in seconds to a human-readable string.
 * @param d - Duration in seconds
 * @returns Formatted string like "1:23.4" or "5.2s"
 */
export function fmtDuration(d: number): string {
    if (!d || !isFinite(d)) return '0:00';
    const m = Math.floor(d / 60);
    const s = Math.floor(d % 60);
    const ms = Math.floor((d % 1) * 10);
    return m > 0 ? `${m}:${s.toString().padStart(2, '0')}.${ms}` : `${s}.${ms}s`;
}
