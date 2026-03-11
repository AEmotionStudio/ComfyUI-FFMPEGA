/**
 * FFMPEGA Sidebar — Node documentation data.
 *
 * Structured documentation for all FFMPEGA nodes, tips & tricks,
 * video editor shortcuts, changelog highlights, and example workflows.
 */

// ── Node docs ───────────────────────────────────────────────────────

export interface NodeDoc {
    /** Internal ComfyUI node type name */
    type: string;
    /** Human-friendly display name */
    title: string;
    /** Short description */
    description: string;
    /** Tips specific to this node */
    tips: string[];
    /** Key inputs to highlight (name → tooltip) */
    inputs: Array<{ name: string; info: string }>;
    /** Related example workflow filenames (without extension) */
    relatedWorkflows?: string[];
}

export const NODE_DOCS: NodeDoc[] = [
    {
        type: "FFMPEGAgent",
        title: "FFMPEG Agent",
        description:
            "AI-powered video editor: describe edits in natural language and the agent generates and runs the FFmpeg pipeline automatically.",
        tips: [
            "Use gemini-cli or claude-cli for zero-cost local inference — no API key needed.",
            "Set llm_model to 'none' and connect an Effects Builder for manual, AI-free editing.",
            "Connect multiple videos to video_a/b/c for concat, split screen, or xfade. New slots appear automatically.",
            "Enable 'Advanced' toggle to access encoding, SAM3, Whisper, FLUX, and batch settings.",
            "Use preview_mode for quick 480p test renders before full quality.",
            "save_output is Off by default — turn it On or connect a Save Video node downstream.",
        ],
        inputs: [
            { name: "prompt", info: "Natural language instruction describing the desired edit." },
            { name: "video_path", info: "Absolute path to the source video file." },
            { name: "llm_model", info: "AI model selection: CLI tools, Ollama (local), cloud APIs, or 'none' for manual mode." },
            { name: "no_llm_mode", info: "What to do when llm_model is 'none': manual, sam3_masking, transcribe, karaoke, generate_audio, lip_sync, animate_portrait, minimax_remover, flux_klein, marigold, video_depth, or ai_upscale." },
            { name: "quality_preset", info: "Output quality: draft (fast), standard (balanced), high (slow), lossless." },
            { name: "images_a", info: "Video as image frames. More slots (images_b, c, …) appear automatically." },
            { name: "audio_a", info: "Audio input. More slots appear automatically." },
            { name: "pipeline_json", info: "Connect from Effects Builder for manual effect composition." },
        ],
        relatedWorkflows: [
            "Colorgrade_Text_Overlay_Ex_v1",
            "Multi_Special_Effects_Ex_v1",
            "Simple_Colograde_Ex_v1",
        ],
    },
    {
        type: "FFMPEGAEffects",
        title: "FFMPEGA Effects Builder",
        description:
            "Compose video effects visually without an LLM. Select effects from categorized dropdowns, choose a preset, add raw FFmpeg filters, and target objects with SAM3.",
        tips: [
            "Right-click the node for 18+ built-in presets (Cinematic, Vintage, Social, etc.).",
            "Chain up to 3 effects — they apply in order (effect_1 → effect_2 → effect_3).",
            "Use sam3_target to apply effects only to detected objects (e.g., 'face', 'person').",
            "The raw_ffmpeg field accepts standard FFmpeg -vf syntax, applied after skill effects.",
            "Connect output to the Agent node's pipeline_json input.",
        ],
        inputs: [
            { name: "preset", info: "Quick-start presets that auto-fill effects and params." },
            { name: "effect_1/2/3", info: "Effects categorized by: 🎨 Visual, ⏱️ Temporal, 📐 Spatial, 🔊 Audio, 📦 Encoding, ✨ Outcome." },
            { name: "raw_ffmpeg", info: "Raw FFmpeg video filter string, applied after skill effects." },
            { name: "sam3_target", info: "Text description of object to mask (e.g., 'the person', 'license plate')." },
        ],
        relatedWorkflows: [
            "Colorhold_VHS_Tensors_Ex_v1",
            "Datamosh_Special_Effects_VHS_Tensors_Ex_v1",
        ],
    },
    {
        type: "FFMPEGALoadVideoPath",
        title: "Load Video Path (FFMPEGA)",
        description:
            "Zero-memory video input with inline preview. Select or upload a video and connect to the Agent's video_a/b/c slots. Uses 0 MB regardless of video length.",
        tips: [
            "Uses ~0 MB vs ~21 GB for a standard Load Video — always prefer this for multi-video workflows.",
            "Supports VHS-style trim params: force_rate, skip_first_frames, frame_load_cap, select_every_nth.",
            "Accepts upstream video_path input for chaining from Save Video nodes.",
            "Also outputs mask_points for SAM3 guided masking via the Point Selector.",
        ],
        inputs: [
            { name: "video", info: "Select or upload a video file — path only, not loaded into memory." },
            { name: "force_rate", info: "Override FPS. 0 = use source FPS." },
            { name: "skip_first_frames", info: "Number of frames to skip from the start." },
            { name: "frame_load_cap", info: "Max frames to use. 0 = all frames." },
        ],
    },
    {
        type: "FFMPEGASaveVideo",
        title: "Save Video (FFMPEGA)",
        description:
            "Zero-memory video output with inline preview. Copies video to output directory and saves a workflow PNG thumbnail alongside it for drag-and-drop workflow loading.",
        tips: [
            "Set save_output to 'Preview Only' to test without saving to disk.",
            "The workflow PNG saved alongside the video lets you drag it back into ComfyUI to reload the workflow.",
            "Outputs IMAGE frames and AUDIO for chaining with downstream nodes.",
        ],
        inputs: [
            { name: "video_path", info: "Path from FFMPEGA Agent or Load Video Path." },
            { name: "filename_prefix", info: "Supports ComfyUI formatting like %date:yyyy-MM-dd%." },
            { name: "save_output", info: "On = save to output folder. Off = preview only." },
        ],
    },
    {
        type: "FFMPEGAFrameExtract",
        title: "Frame Extract (FFMPEGA)",
        description:
            "Extract individual frames and audio from a video at a specified frame rate, time range, and frame limit.",
        tips: [
            "Set fps=1 to extract one frame per second — good for thumbnails or analysis.",
            "Accepts upstream video_path from Save Video or Load Video Path nodes.",
            "max_frames caps output to prevent memory issues with long videos.",
        ],
        inputs: [
            { name: "video_path", info: "Absolute path to video file." },
            { name: "fps", info: "Extraction rate. 1.0 = one frame/sec, 30 = every frame at 30fps." },
            { name: "start_time", info: "Start time in seconds." },
            { name: "duration", info: "Duration to extract. 0 = full video." },
            { name: "max_frames", info: "Maximum frames to return (default 100)." },
        ],
    },
    {
        type: "FFMPEGAMediaBridge",
        title: "Media Bridge (FFMPEGA)",
        description:
            "Bidirectional media switch: convert IMAGE tensors to a video file path, or decode a video path back to IMAGE + AUDIO. Lightweight alternative to full Load/Save nodes.",
        tips: [
            "images_to_path: insert between Load Video Upload and the Agent to free tensors early.",
            "path_to_images: quickly decode a video path into frames for downstream image processing.",
            "Audio is automatically extracted (path_to_images) or muxed in (images_to_path) when connected.",
            "Outputs fps and frame_count in both modes for easy downstream use.",
        ],
        inputs: [
            { name: "mode", info: "images_to_path or path_to_images — pick the conversion direction." },
            { name: "images", info: "IMAGE tensor input (used in images_to_path mode)." },
            { name: "video_path", info: "Video file path input (used in path_to_images mode)." },
            { name: "fps", info: "Encoding FPS for images_to_path mode (default 24)." },
            { name: "audio", info: "Optional audio to mux into the video (images_to_path mode)." },
        ],
    },
    {
        type: "FFMPEGALoadImagePath",
        title: "Load Image Path (FFMPEGA)",
        description:
            "Zero-memory image loader — outputs a file path instead of an IMAGE tensor. Uses ~0 MB for any number of images.",
        tips: [
            "Uses ~0 MB vs ~6 MB per image with standard Load Image.",
            "Connect to Agent's image_path_a/b/c inputs for overlay, grid, or slideshow workflows.",
            "Supports the Point Selector for SAM3 guided masking.",
        ],
        inputs: [
            { name: "image", info: "Select or upload an image from ComfyUI's input directory." },
        ],
    },
    {
        type: "FFMPEGATextInput",
        title: "FFMPEGA Text",
        description:
            "Flexible text input for subtitles, overlays, watermarks, and title cards with auto-mode detection.",
        tips: [
            "Paste SRT-formatted text and it auto-detects as subtitle mode.",
            "Short single-line text auto-detects as watermark, multi-line as subtitle.",
            "Right-click for 10 built-in presets (SRT Example, Bold Watermark, Title Card, etc.).",
            "Connect to Agent's text_a/b/c inputs — multiple text nodes can be connected.",
        ],
        inputs: [
            { name: "text", info: "Text content — plain text, SRT subtitles, or watermark text." },
            { name: "mode", info: "auto, subtitle, overlay, watermark, title_card, or raw." },
            { name: "position", info: "auto, center, top, bottom, top_left, bottom_right, etc." },
            { name: "font_size", info: "0 = auto (24 for subtitles, 48 for overlay, 20 for watermark)." },
        ],
        relatedWorkflows: [
            "Colorgrade_Text_Overlay_Ex_v1",
            "Subtitle_Burn_Ex_v1",
        ],
    },
    {
        type: "FFMPEGAPreview",
        title: "FFMPEGA Preview",
        description: "Quick video preview node for inspecting intermediate results.",
        tips: ["Use for debugging — preview any video_path in the pipeline without saving."],
        inputs: [],
    },
    {
        type: "FFMPEGAVideoInfo",
        title: "FFMPEGA Video Info",
        description: "Analyze a video and output metadata: resolution, FPS, duration, codec, and frame count.",
        tips: ["Outputs structured metadata for use in conditional or parametric workflows."],
        inputs: [],
    },
    {
        type: "LoadLastImage",
        title: "Load Last Image (FFMPEGA)",
        description: "Automatically loads the most recently saved image from ComfyUI's output directory.",
        tips: ["Useful for iterative workflows — always picks up the latest result."],
        inputs: [],
    },
    {
        type: "LoadLastVideo",
        title: "Load Last Video (FFMPEGA)",
        description: "Automatically loads the most recently saved video from ComfyUI's output directory.",
        tips: ["Useful for chaining workflows — process the latest output again with different effects."],
        inputs: [],
    },
    {
        type: "FFMPEGAVideoEditor",
        title: "Video Editor (FFMPEGA)",
        description:
            "Interactive NLE (Non-Linear Editor) for hands-on video editing directly inside ComfyUI. Full-screen modal with timeline, transport controls, and editing tools — no LLM required.",
        tips: [
            "Press '?' in the editor to see all keyboard shortcuts.",
            "Use 'S' to split segments at the playhead.",
            "Speed control supports 0.25x–4x per segment.",
            "Text overlays support configurable font size, color, and timing.",
            "Transitions (crossfade, dip-to-black) are added between segments.",
            "Ctrl+Z / Ctrl+Shift+Z for undo/redo.",
        ],
        inputs: [
            { name: "video_path", info: "Path to video file to edit." },
            { name: "images", info: "Video frames from upstream nodes." },
            { name: "audio", info: "Audio input for the editor." },
        ],
    },
];

// ── Tips & Tricks ───────────────────────────────────────────────────

export interface TipCategory {
    title: string;
    icon: string;
    tips: string[];
}

export const TIPS_AND_TRICKS: TipCategory[] = [
    {
        title: "Performance",
        icon: "⚡",
        tips: [
            "Use Load Video Path instead of Load Video Upload — it uses 0 MB vs ~21 GB for long videos.",
            "Use Media Bridge between Load Video Upload and the Agent to free tensors early.",
            "Set quality_preset to 'draft' for quick test renders, then switch to 'high' for final output.",
            "preview_mode renders at 480p for the first 10 seconds — great for quick checks.",
            "Run Whisper on CPU (whisper_device='cpu') if you're low on VRAM.",
            "Disable FLUX Klein (use_flux_klein=Off) to save 8–15 GB VRAM — MiniMax-Remover, LaMa + FFmpeg fallbacks work well.",
            "Enable MiniMax-Remover (use_minimax_remover=On) for high-quality video object removal (~5–8 GB VRAM). Takes priority over FLUX Klein for removal.",
            "Use file-path inputs (video_a, image_path_a) instead of tensor inputs for multi-video workflows.",
        ],
    },
    {
        title: "Common Pitfalls",
        icon: "⚠️",
        tips: [
            "Don't enable save_output on both the Agent AND a downstream Save Video — you'll get duplicate files.",
            "If using cloud API models (GPT, Claude, Gemini), you need an api_key. CLI models don't need one.",
            "The Effects Builder output must connect to the Agent's pipeline_json input, not video_path.",
            "For concat/xfade, connect videos to video_a/b/c slots — not the main video_path input.",
            "SAM3 requires GPU — there is no CPU fallback for video segmentation.",
            "When chaining nodes, the video_path output is a STRING — connect it to STRING inputs only.",
        ],
    },
    {
        title: "Advanced Techniques",
        icon: "🔬",
        tips: [
            "Chain an Effects Builder → Agent with llm_model='none' for precise manual control.",
            "Use no_llm_mode='sam3_masking' with a text prompt to blur/remove specific objects without AI.",
            "Connect multiple Text nodes (text_a, text_b) for multi-line subtitles or positioned overlays.",
            "Use no_llm_mode='transcribe' or 'karaoke_subtitles' for automatic speech-to-text subtitles.",
            "Batch mode processes an entire folder of videos with one LLM call — great for consistent edits.",
            "Custom LUT files (.cube/.3dl) dropped in the luts/ folder are auto-discovered by the Agent.",
            "Enable verify_output for complex edits — the Agent inspects and auto-corrects output quality.",
            "Use mask_points from Load Video Path to guide SAM3 with click-to-select instead of text prompts.",
        ],
    },
];

// ── Video Editor Shortcuts ──────────────────────────────────────────

export interface Shortcut {
    key: string;
    action: string;
}

export const EDITOR_SHORTCUTS: Shortcut[] = [
    { key: "Space", action: "Play / Pause" },
    { key: "J", action: "Shuttle reverse" },
    { key: "K", action: "Pause" },
    { key: "L", action: "Shuttle forward" },
    { key: "I", action: "Mark In point" },
    { key: "O", action: "Mark Out point" },
    { key: "←", action: "Step back 1 frame" },
    { key: "→", action: "Step forward 1 frame" },
    { key: "S", action: "Split at playhead" },
    { key: "V", action: "Select tool" },
    { key: "Delete", action: "Delete selected segment" },
    { key: "Ctrl+Z", action: "Undo" },
    { key: "Ctrl+Shift+Z", action: "Redo" },
    { key: "?", action: "Show shortcut overlay" },
];

// ── Changelog Highlights ────────────────────────────────────────────

export interface ChangelogEntry {
    version: string;
    date: string;
    highlights: string[];
}

export const CHANGELOG_HIGHLIGHTS: ChangelogEntry[] = [
    {
        version: "2.14.0",
        date: "2026-03-08",
        highlights: [
            "Video Editor Node — interactive NLE for hands-on editing inside ComfyUI",
            "Seekable MP4 preview server with HTTP Range support",
            "TypeScript migration for Video Editor frontend",
            "1,056 tests, 0 failures",
        ],
    },
    {
        version: "2.13.0",
        date: "2026-03-06",
        highlights: [
            "FLUX Klein toggle — disable to save 8–15 GB VRAM",
            "Edit FFmpeg fallback with 22 keyword-matched filters",
            "AI Background Removal with BRIA RMBG (6 model choices)",
            "952 tests, 0 failures",
        ],
    },
    {
        version: "2.12.0",
        date: "2026-03-06",
        highlights: [
            "AI Face Animation (LivePortrait) with motion transfer",
            "LivePortrait no-LLM mode for direct face animation",
            "LaMa safetensors conversion for improved security",
            "939 tests, 0 failures",
        ],
    },
];

// ── Example Workflows ───────────────────────────────────────────────

export interface ExampleWorkflow {
    filename: string;
    title: string;
    description: string;
}

export const EXAMPLE_WORKFLOWS: ExampleWorkflow[] = [
    { filename: "4x4_Video_Grid_Ex_v1", title: "4×4 Video Grid", description: "Combine 4 videos into a grid layout" },
    { filename: "Bouncing_Logo_Animation_Ex_v1", title: "Bouncing Logo Animation", description: "Animated logo overlay with bounce motion" },
    { filename: "Colorgrade_Text_Overlay_Ex_v1", title: "Color Grade + Text Overlay", description: "Apply color grading with text effects" },
    { filename: "Colorhold_VHS_Tensors_Ex_v1", title: "Color Hold + VHS Effect", description: "Isolate a color and apply VHS distortion" },
    { filename: "Datamosh_Special_Effects_VHS_Tensors_Ex_v1", title: "Datamosh + Special Effects", description: "Datamosh glitch effects with VHS overlay" },
    { filename: "Greenscreen_Remove_VHS_Tensors_Ex_v1", title: "Green Screen Removal", description: "Chroma key background removal" },
    { filename: "Multi_Special_Effects_Ex_v1", title: "Multi Special Effects", description: "Chain multiple visual effects together" },
    { filename: "PiP_Video_Overlay_Example_v1", title: "Picture-in-Picture Overlay", description: "Overlay a video on top of another" },
    { filename: "Simple_Colograde_Ex_v1", title: "Simple Color Grade", description: "Basic color grading workflow" },
    { filename: "Slideshow_Audio_Example_v1", title: "Slideshow with Audio", description: "Image slideshow with background music" },
    { filename: "Subtitle_Burn_Ex_v1", title: "Subtitle Burn-In", description: "Burn SRT subtitles into video" },
];

// ── External Links ──────────────────────────────────────────────────

export interface ExternalLink {
    label: string;
    url: string;
    icon: string;
}

export const EXTERNAL_LINKS: ExternalLink[] = [
    { label: "GitHub Repository", url: "https://github.com/AEmotionStudio/ComfyUI-FFMPEGA", icon: "🔗" },
    { label: "Report Issues", url: "https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/issues", icon: "🐛" },
    { label: "Changelog", url: "https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/blob/main/CHANGELOG.md", icon: "📋" },
    { label: "Skills Reference", url: "https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/blob/main/SKILLS_REFERENCE.md", icon: "📖" },
];
