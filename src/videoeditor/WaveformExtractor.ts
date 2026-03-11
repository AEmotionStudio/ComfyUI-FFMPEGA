/**
 * WaveformExtractor — extract audio waveform peaks from a video file.
 *
 * Tries the server-side `/ffmpega/waveform` endpoint first (lightweight —
 * returns ~8 KB of JSON peaks without the client downloading the full
 * video).  Falls back to client-side Web Audio API extraction if the
 * server endpoint is unavailable.
 *
 * Results are cached by video path to avoid re-extraction on subsequent opens.
 */

const PEAK_COUNT = 2000;  // Number of peak bins for waveform display
const WAVEFORM_ROUTE = '/ffmpega/waveform';

/**
 * Max file size (bytes) for client-side fallback extraction.
 * Only used when the server endpoint fails.
 */
const MAX_FETCH_SIZE = 50 * 1024 * 1024;  // 50 MB

/** Cached waveform data keyed by video path */
const waveformCache = new Map<string, WaveformData>();

export interface WaveformData {
    peaks: Float32Array;
    duration: number;
    sampleRate: number;
}

/**
 * Extract waveform peaks for a video at the given path.
 *
 * Tries server-side extraction first (efficient — only audio is processed
 * server-side via FFmpeg), then falls back to client-side Web Audio API.
 *
 * @param videoPath - raw video path (as passed to /ffmpega/preview?path=...)
 * @param previewUrl - optional preview URL for client-side fallback
 * @returns WaveformData with normalized peaks (0–1)
 */
export async function extractWaveform(
    videoPath: string,
    previewUrl?: string,
): Promise<WaveformData> {
    // Check cache first (keyed by videoPath)
    const cached = waveformCache.get(videoPath);
    if (cached) {
        return cached;
    }

    // Try server-side extraction first
    try {
        const result = await _fetchServerWaveform(videoPath);
        if (result) {
            waveformCache.set(videoPath, result);
            return result;
        }
    } catch (e) {
        console.warn('[WaveformExtractor] Server extraction failed, trying client-side:', e);
    }

    // Fall back to client-side extraction.
    // Cache the result even if it's a flat fallback — this prevents
    // repeated futile fetch attempts for files where both paths fail.
    const fallbackUrl = previewUrl || videoPath;
    const fallbackResult = await _extractClientSide(fallbackUrl);
    waveformCache.set(videoPath, fallbackResult);
    return fallbackResult;
}

/**
 * Fetch waveform peaks from the server-side endpoint.
 * Returns null if the endpoint is unavailable or fails.
 */
async function _fetchServerWaveform(videoPath: string): Promise<WaveformData | null> {
    const url = `${WAVEFORM_ROUTE}?path=${encodeURIComponent(videoPath)}`;
    const resp = await fetch(url);

    if (!resp.ok) {
        return null;
    }

    const data = await resp.json();
    if (!data.peaks || !Array.isArray(data.peaks) || data.peaks.length === 0) {
        return null;
    }

    // Convert JSON array to Float32Array
    const peaks = new Float32Array(data.peaks);

    return {
        peaks,
        duration: data.duration || 0,
        sampleRate: data.sampleRate || 0,
    };
}

/**
 * Client-side fallback: fetch the full video and decode audio via Web Audio API.
 * Only used when the server endpoint is unavailable.
 */
async function _extractClientSide(
    fetchUrl: string,
): Promise<WaveformData> {
    const flat: WaveformData = {
        peaks: new Float32Array(PEAK_COUNT).fill(0.1),
        duration: 0,
        sampleRate: 0,
    };

    try {
        // Pre-flight: check file size via HEAD to avoid OOM on large videos.
        try {
            const head = await fetch(fetchUrl, { method: 'HEAD' });
            const contentLength = head.headers.get('content-length');
            if (contentLength) {
                const size = parseInt(contentLength, 10);
                if (size > MAX_FETCH_SIZE) {
                    console.warn(
                        `[WaveformExtractor] File too large for client-side extraction ` +
                        `(${(size / 1024 / 1024).toFixed(0)}MB > ${MAX_FETCH_SIZE / 1024 / 1024}MB limit). ` +
                        `Showing flat waveform.`,
                    );
                    return flat;
                }
            }
        } catch {
            // HEAD not supported or network error — proceed with GET
        }

        const response = await fetch(fetchUrl);
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

        const result: WaveformData = {
            peaks,
            duration: audioBuffer.duration,
            sampleRate: audioBuffer.sampleRate,
        };

        return result;
    } catch (e) {
        console.warn('[WaveformExtractor] Client-side extraction failed:', e);
        return flat;
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
