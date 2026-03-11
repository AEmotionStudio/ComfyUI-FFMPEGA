/**
 * WaveformExtractor — extract audio waveform peaks from a video file
 * using the Web Audio API.
 *
 * Fetches the video as an ArrayBuffer, decodes the audio track,
 * and downsamples to a fixed number of peak bins for efficient rendering.
 * Results are cached by URL to avoid re-decoding on subsequent opens.
 */

const PEAK_COUNT = 2000;  // Number of peak bins for waveform display

/** Cached waveform data (full WaveformData so duration/sampleRate survive cache hits) */
const waveformCache = new Map<string, WaveformData>();

export interface WaveformData {
    peaks: Float32Array;
    duration: number;
    sampleRate: number;
}

/**
 * Extract waveform peaks from a video/audio URL.
 *
 * @param url - URL to fetch the media from (e.g., /ffmpega/preview?path=...)
 * @returns WaveformData with normalized peaks (0–1)
 */
export async function extractWaveform(url: string): Promise<WaveformData> {
    // Check cache first
    const cached = waveformCache.get(url);
    if (cached) {
        return cached;
    }

    try {
        // TODO: This fetches the entire video file into memory just to decode audio.
        // For large videos (500MB+) this can OOM. Consider a server-side endpoint
        // that serves only the audio track, or use MediaSource + createMediaElementSource
        // for streaming decode.
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Failed to fetch: ${response.status}`);
        }
        const arrayBuffer = await response.arrayBuffer();

        // Decode audio
        const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
        let audioBuffer: AudioBuffer;
        try {
            audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
        } finally {
            audioCtx.close();
        }

        // Extract peaks from channel 0 (mono or left channel)
        const channelData = audioBuffer.getChannelData(0);
        const peaks = downsamplePeaks(channelData, PEAK_COUNT);

        // Cache the full result (including duration/sampleRate)
        const result: WaveformData = {
            peaks,
            duration: audioBuffer.duration,
            sampleRate: audioBuffer.sampleRate,
        };
        waveformCache.set(url, result);

        return result;
    } catch (e) {
        console.warn('[WaveformExtractor] Failed to extract waveform:', e);
        // Return a flat waveform as fallback
        const fallback = new Float32Array(PEAK_COUNT).fill(0.1);
        return { peaks: fallback, duration: 0, sampleRate: 0 };
    }
}

/**
 * Downsample raw audio samples to a fixed number of peak values.
 * Each bin stores the max absolute amplitude in that range.
 */
function downsamplePeaks(channelData: Float32Array, binCount: number): Float32Array {
    const peaks = new Float32Array(binCount);
    const samplesPerBin = Math.floor(channelData.length / binCount);

    if (samplesPerBin === 0) {
        // Very short audio — fill with what we have
        for (let i = 0; i < Math.min(channelData.length, binCount); i++) {
            peaks[i] = Math.abs(channelData[i]);
        }
        return peaks;
    }

    for (let bin = 0; bin < binCount; bin++) {
        const start = bin * samplesPerBin;
        const end = Math.min(start + samplesPerBin, channelData.length);
        let max = 0;
        for (let i = start; i < end; i++) {
            const abs = Math.abs(channelData[i]);
            if (abs > max) max = abs;
        }
        peaks[bin] = max;
    }

    // Normalize to 0–1
    let globalMax = 0;
    for (let i = 0; i < binCount; i++) {
        if (peaks[i] > globalMax) globalMax = peaks[i];
    }
    if (globalMax > 0) {
        for (let i = 0; i < binCount; i++) {
            peaks[i] /= globalMax;
        }
    }

    return peaks;
}

/** Clear the waveform cache */
export function clearWaveformCache(): void {
    waveformCache.clear();
}
