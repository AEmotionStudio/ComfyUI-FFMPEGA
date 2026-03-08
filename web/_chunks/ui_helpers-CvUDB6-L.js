function createUploadButton(acceptTypes) {
  const fileInput = document.createElement("input");
  Object.assign(fileInput, {
    type: "file",
    accept: acceptTypes,
    style: "display: none"
  });
  const uploadBtn = document.createElement("button");
  uploadBtn.innerHTML = "Upload Video...";
  uploadBtn.setAttribute("aria-label", "Upload Video");
  uploadBtn.style.cssText = `
        width: 100%;
        background-color: #222;
        color: #ccc;
        border: 1px solid #333;
        border-radius: 4px;
        padding: 6px;
        cursor: pointer;
        font-family: monospace;
        font-size: 12px;
        transition: background-color 0.2s;
    `;
  let isHovered = false;
  let isFocused = false;
  const updateBtnStyle = () => {
    if (uploadBtn.disabled) return;
    const active = isHovered || isFocused;
    uploadBtn.style.backgroundColor = active ? "#333" : "#222";
    uploadBtn.style.outline = isFocused ? "2px solid #4a6a8a" : "none";
    uploadBtn.style.outlineOffset = isFocused ? "2px" : "0px";
  };
  uploadBtn.onmouseenter = () => {
    isHovered = true;
    updateBtnStyle();
  };
  uploadBtn.onmouseleave = () => {
    isHovered = false;
    updateBtnStyle();
  };
  uploadBtn.onfocus = () => {
    isFocused = true;
    updateBtnStyle();
  };
  uploadBtn.onblur = () => {
    isFocused = false;
    updateBtnStyle();
  };
  uploadBtn.onclick = () => {
    fileInput.click();
  };
  uploadBtn.onpointerdown = (e) => {
    e.stopPropagation();
  };
  return { fileInput, uploadBtn, updateBtnStyle };
}
const SLOT_LABELS = "abcdefghijklmnopqrstuvwxyz";
const RANDOM_PROMPTS = [
  "Make it cinematic with a fade in and vignette",
  "Apply VHS effect, slow it down to 0.75x, add echo",
  "Horror style, reverse the video, add fade out",
  "Trim to first 15 seconds, make it vertical for TikTok, add text 'Follow me!' at the bottom",
  "Apply edge detection with colorful mode, boost saturation",
  "Normalize audio, compress for web, resize to 1080p",
  "Lofi style, slow down to 0.8x, muffle the audio",
  "Anime look, add text 'Episode 1' at the top",
  "Make it look like underwater footage with echo on the audio",
  "Day for night effect, add vignette, reduce noise",
  "Pixelate it, posterize with 3 levels, speed up 1.5x",
  "Cyberpunk style with strong sharpening and neon glow",
  "Surveillance look, add text 'CAM 01' in top left, resize to 720p",
  "Noir style, add fade in, slow zoom",
  "Speed up 4x, apply dreamy effect, add fade in and out",
  "Show audio waveform at the bottom with cyan color",
  "Arrange these images in a 3-column grid with gaps",
  "Create a slideshow with 4 seconds per image and fade transitions",
  "Overlay the logo image in the bottom-right corner at 20% scale",
  "Add a typewriter text 'Coming Soon' with scrolling credits",
  "Apply tilt-shift miniature effect and boost saturation",
  "Extract a thumbnail at the 5 second mark",
  "Add a news ticker that says 'Breaking News' at the bottom",
  "Cross dissolve transition between both clips with 1 second overlap",
  "Blur a face region for privacy and normalize loudness",
  "Apply datamosh glitch art effect with film grain overlay",
  "Create a sprite sheet preview of the video",
  "Replace the audio with the connected audio track",
  "Add a lower third with name 'John Smith' and title 'Director'",
  "Apply golden hour warm glow with a slow Ken Burns zoom"
];
function updateDynamicSlots(node, prefix, slotType, excludePrefix = []) {
  const excludes = Array.isArray(excludePrefix) ? excludePrefix : [excludePrefix];
  const matchingIndices = [];
  for (let i = 0; i < node.inputs.length; i++) {
    const name = node.inputs[i].name;
    if (name.startsWith(prefix)) {
      if (excludes.some((ep) => name.startsWith(ep))) continue;
      matchingIndices.push(i);
    }
  }
  if (matchingIndices.length === 0) return;
  let lastConnectedGroupIdx = -1;
  for (let g = matchingIndices.length - 1; g >= 0; g--) {
    const slotIdx = matchingIndices[g];
    if (node.inputs[slotIdx].link != null) {
      lastConnectedGroupIdx = g;
      break;
    }
  }
  const needed = lastConnectedGroupIdx + 2;
  while (matchingIndices.length < needed) {
    const letter = SLOT_LABELS[matchingIndices.length];
    if (!letter) break;
    const newName = `${prefix}${letter}`;
    node.addInput(newName, slotType);
    matchingIndices.push(node.inputs.length - 1);
  }
  while (matchingIndices.length > needed && matchingIndices.length > 1) {
    const lastGroupIdx = matchingIndices.length - 1;
    const slotIdx = matchingIndices[lastGroupIdx];
    if (node.inputs[slotIdx].link != null) break;
    node.removeInput(slotIdx);
    matchingIndices.pop();
  }
}
function handlePaste(node, replace) {
  if (navigator.clipboard && navigator.clipboard.readText) {
    navigator.clipboard.readText().then((text) => {
      if (text) {
        setPrompt(node, text, replace, "#4a6a8a");
      }
    }).catch((err) => {
      console.error("Failed to read clipboard", err);
      flashNode(node, "#7a4a4a");
    });
  } else {
    flashNode(node, "#7a4a4a");
  }
}
function setPrompt(node, text, replace = false, color = "#4a5a7a") {
  var _a;
  const promptWidget = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "prompt");
  if (promptWidget) {
    if (replace) {
      if (promptWidget.value && String(promptWidget.value).trim() !== "") {
        node._previousPrompt = String(promptWidget.value);
      }
      promptWidget.value = text;
    } else {
      const currentText = String(promptWidget.value ?? "");
      if (!currentText || currentText.trim() === "") {
        promptWidget.value = text;
      } else if (!currentText.includes(text)) {
        promptWidget.value = currentText.trim() + " and " + text;
      }
    }
    node.setDirtyCanvas(true, true);
    flashNode(node, color);
  }
}
function flashNode(node, color = "#4a5a7a") {
  if (!node || node._isFlashing) return;
  node._isFlashing = true;
  const originalBg = node.bgcolor;
  node.bgcolor = color;
  node.setDirtyCanvas(true, true);
  setTimeout(() => {
    if (node.bgcolor === color) {
      node.bgcolor = originalBg;
    }
    node._isFlashing = false;
    node.setDirtyCanvas(true, true);
  }, 350);
}
function addVideoPreviewMenu(node, videoEl, previewContainer, _previewWidget, getVideoUrl, infoEl) {
  const currentGetExtra = node.getExtraMenuOptions;
  node.getExtraMenuOptions = function(_canvas, options) {
    currentGetExtra == null ? void 0 : currentGetExtra.apply(this, arguments);
    const optNew = [];
    const url = getVideoUrl();
    const hasVideo = !!url && previewContainer.style.display !== "none";
    optNew.push({
      content: "🔄 Sync Preview",
      callback: () => {
        const videos = previewContainer.querySelectorAll("video");
        videos.forEach((v) => {
          if (v.src) {
            const oldSrc = v.src;
            v.src = "";
            v.src = oldSrc;
            v.play().catch(() => {
            });
          }
        });
        flashNode(node, "#4a7a4a");
      }
    });
    if (hasVideo) {
      optNew.push(
        {
          content: "🗒 Copy Video URL",
          callback: () => {
            navigator.clipboard.writeText(url).catch(() => {
            });
            flashNode(node, "#4a5a7a");
          }
        },
        {
          content: "📏 Jump: Start",
          callback: () => {
            videoEl.currentTime = 0;
            videoEl.play().catch(() => {
            });
            flashNode(node, "#4a5a7a");
          }
        },
        {
          content: "📏 Jump: Middle",
          callback: () => {
            const dur = videoEl.duration;
            if (dur && isFinite(dur)) {
              videoEl.currentTime = dur / 2;
            }
            flashNode(node, "#4a5a7a");
          }
        },
        {
          content: "📏 Jump: End",
          callback: () => {
            const dur = videoEl.duration;
            if (dur && isFinite(dur)) {
              videoEl.currentTime = Math.max(dur - 0.5, 0);
            }
            flashNode(node, "#4a5a7a");
          }
        }
      );
      optNew.push({
        content: "📸 Snapshot",
        submenu: {
          options: [
            {
              content: "Copy Frame to Clipboard",
              callback: async () => {
                try {
                  const c = document.createElement("canvas");
                  c.width = videoEl.videoWidth;
                  c.height = videoEl.videoHeight;
                  const ctx = c.getContext("2d");
                  if (!ctx) throw new Error("Canvas 2D context unavailable");
                  ctx.drawImage(videoEl, 0, 0);
                  const blob = await new Promise((r) => c.toBlob(r, "image/png"));
                  if (!blob) throw new Error("toBlob returned null");
                  await navigator.clipboard.write([
                    new ClipboardItem({ "image/png": blob })
                  ]);
                  flashNode(node, "#4a7a4a");
                } catch (e) {
                  console.error("Snapshot failed:", e);
                  flashNode(node, "#7a4a4a");
                }
              }
            },
            {
              content: "Download Frame as PNG",
              callback: () => {
                try {
                  const c = document.createElement("canvas");
                  c.width = videoEl.videoWidth;
                  c.height = videoEl.videoHeight;
                  const ctx = c.getContext("2d");
                  if (!ctx) throw new Error("Canvas 2D context unavailable");
                  ctx.drawImage(videoEl, 0, 0);
                  const a = document.createElement("a");
                  a.href = c.toDataURL("image/png");
                  a.download = "frame.png";
                  document.body.appendChild(a);
                  a.click();
                  setTimeout(() => a.remove(), 0);
                  flashNode(node, "#4a7a4a");
                } catch (e) {
                  console.error("Download failed:", e);
                  flashNode(node, "#7a4a4a");
                }
              }
            }
          ]
        }
      });
      optNew.push({
        content: "⚡ Playback Speed",
        submenu: {
          options: [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 4].map((s) => ({
            content: `${s}×`,
            callback: () => {
              videoEl.playbackRate = s;
              flashNode(node, "#4a5a7a");
            }
          }))
        }
      });
      optNew.push({
        content: "📊 Video Info",
        submenu: {
          options: [
            {
              content: "Copy Full Info",
              callback: () => {
                const dur = videoEl.duration;
                const line = [
                  `URL: ${url}`,
                  `Resolution: ${videoEl.videoWidth}×${videoEl.videoHeight}`,
                  `Duration: ${dur ? dur.toFixed(2) + "s" : "N/A"}`,
                  `Current Time: ${videoEl.currentTime.toFixed(2)}s`,
                  `Playback Rate: ${videoEl.playbackRate}×`,
                  `Muted: ${videoEl.muted}`,
                  `Loop: ${videoEl.loop}`
                ].join("\n");
                navigator.clipboard.writeText(line).catch(() => {
                });
                flashNode(node, "#4a5a7a");
              }
            }
          ]
        }
      });
      optNew.push({
        content: "💾 Download Video",
        callback: () => {
          const a = document.createElement("a");
          a.href = url;
          a.download = "video.mp4";
          try {
            const params = new URL(a.href, window.location.href).searchParams;
            const f = params.get("filename");
            if (f) a.download = f;
          } catch {
          }
          document.body.appendChild(a);
          a.click();
          setTimeout(() => a.remove(), 0);
          flashNode(node, "#4a7a4a");
        }
      });
    }
    options.unshift(...optNew, null);
  };
}
function addDownloadOverlay(container, videoEl) {
  const btn = document.createElement("button");
  btn.innerHTML = `<span aria-hidden="true">💾</span>`;
  btn.title = "Save Video";
  btn.type = "button";
  btn.setAttribute("aria-label", "Save Video");
  btn.className = "ffmpega-overlay-btn";
  btn.style.cssText = `
        position: absolute;
        top: 8px;
        right: 8px;
        background: rgba(0, 0, 0, 0.6);
        color: white;
        border: none;
        padding: 0;
        margin: 0;
        border-radius: 4px;
        width: 28px;
        height: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        font-size: 16px;
        opacity: 0;
        transition: opacity 0.2s, background 0.2s;
        z-index: 10;
        pointer-events: auto;
    `;
  let containerHover = false;
  let btnHover = false;
  let btnFocus = false;
  const updateStyle = () => {
    const isVisible = containerHover || btnFocus || btnHover;
    const isActive = btnHover || btnFocus;
    btn.style.opacity = isVisible ? "1" : "0";
    btn.style.background = isActive ? "rgba(0, 0, 0, 0.8)" : "rgba(0, 0, 0, 0.6)";
    btn.style.outline = btnFocus ? "2px solid #4a6a8a" : "none";
    btn.style.outlineOffset = btnFocus ? "2px" : "0px";
  };
  container.addEventListener("mouseenter", () => {
    containerHover = true;
    updateStyle();
  });
  container.addEventListener("mouseleave", () => {
    containerHover = false;
    updateStyle();
  });
  btn.addEventListener("mouseenter", () => {
    btnHover = true;
    updateStyle();
  });
  btn.addEventListener("mouseleave", () => {
    btnHover = false;
    updateStyle();
  });
  btn.addEventListener("focus", () => {
    btnFocus = true;
    updateStyle();
  });
  btn.addEventListener("blur", () => {
    btnFocus = false;
    updateStyle();
  });
  btn.onclick = (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (videoEl.src) {
      const a = document.createElement("a");
      a.href = videoEl.src;
      a.download = "video.mp4";
      try {
        const params = new URL(a.href, window.location.href).searchParams;
        const f = params.get("filename");
        if (f) a.download = f;
      } catch {
      }
      document.body.appendChild(a);
      a.click();
      setTimeout(() => a.remove(), 0);
      if (btn._timeout) clearTimeout(btn._timeout);
      btn.innerHTML = `<span aria-hidden="true">✅</span>`;
      btn.setAttribute("aria-label", "Saved!");
      btn._timeout = setTimeout(() => {
        btn.innerHTML = `<span aria-hidden="true">💾</span>`;
        btn.setAttribute("aria-label", "Save Video");
        btn._timeout = null;
      }, 1e3);
    }
  };
  container.appendChild(btn);
}
export {
  RANDOM_PROMPTS as R,
  SLOT_LABELS as S,
  addDownloadOverlay as a,
  addVideoPreviewMenu as b,
  createUploadButton as c,
  flashNode as f,
  handlePaste as h,
  setPrompt as s,
  updateDynamicSlots as u
};
