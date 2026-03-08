import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
const THUMB_SIZE = 64;
const THUMB_GAP = 4;
const STRIP_BG = "#1a1a1a";
const STRIP_BORDER = "#333";
const PIN_HIGHLIGHT = "#4a9eff";
const HOVER_HIGHLIGHT = "#2a2a2a";
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}
app.registerExtension({
  name: "LoadLast.ContactSheet",
  beforeRegisterNodeDef(nodeType, nodeData, _app) {
    if (nodeData.name !== "LoadLastImage") return;
    const origOnNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      origOnNodeCreated == null ? void 0 : origOnNodeCreated.apply(this, arguments);
      this._thumbs = [];
      this._hoveredIndex = -1;
      this._pinnedIteration = 0;
      this._stripScrollX = 0;
      const widget = this.addCustomWidget({
        name: "contact_sheet",
        type: "custom",
        value: "",
        draw: (ctx, _node, width, y) => {
          this._drawContactSheet(ctx, width, y);
        },
        computeSize: () => [0, THUMB_SIZE + 16]
      });
      this._contactSheetWidget = widget;
    };
    const origOnExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function(output) {
      origOnExecuted == null ? void 0 : origOnExecuted.apply(this, arguments);
      if (output == null ? void 0 : output.thumbnails) {
        this._thumbs = output.thumbnails.map((t) => ({
          filename: t.filename,
          subfolder: t.subfolder || "",
          type: t.type || "temp",
          iteration: t.iteration || 0,
          loaded: false,
          image: null
        }));
        for (const thumb of this._thumbs) {
          const img = new Image();
          const params = new URLSearchParams({
            filename: thumb.filename,
            subfolder: thumb.subfolder,
            type: thumb.type
          });
          img.src = api.apiURL(`/view?${params.toString()}`);
          img.onload = () => {
            thumb.loaded = true;
            thumb.image = img;
            this.setDirtyCanvas(true, false);
          };
        }
        this.setDirtyCanvas(true, false);
      }
    };
    nodeType.prototype._drawContactSheet = function(ctx, nodeWidth, y) {
      if (!this._thumbs.length) return;
      const stripY = y + 4;
      const stripH = THUMB_SIZE + 8;
      const contentW = nodeWidth - 20;
      ctx.fillStyle = STRIP_BG;
      ctx.strokeStyle = STRIP_BORDER;
      ctx.lineWidth = 1;
      roundRect(ctx, 10, stripY, contentW, stripH, 4);
      ctx.fill();
      ctx.stroke();
      ctx.save();
      ctx.beginPath();
      ctx.rect(12, stripY + 2, contentW - 4, stripH - 4);
      ctx.clip();
      const startX = 14 - this._stripScrollX;
      for (let i = 0; i < this._thumbs.length; i++) {
        const thumb = this._thumbs[i];
        const x = startX + i * (THUMB_SIZE + THUMB_GAP);
        if (x + THUMB_SIZE < 10 || x > nodeWidth) continue;
        if (i === this._hoveredIndex) {
          ctx.fillStyle = HOVER_HIGHLIGHT;
          ctx.fillRect(x - 1, stripY + 3, THUMB_SIZE + 2, THUMB_SIZE + 2);
        }
        if (thumb.iteration === this._pinnedIteration && this._pinnedIteration > 0) {
          ctx.strokeStyle = PIN_HIGHLIGHT;
          ctx.lineWidth = 2;
          ctx.strokeRect(x - 1, stripY + 3, THUMB_SIZE + 2, THUMB_SIZE + 2);
          ctx.lineWidth = 1;
        }
        if (thumb.loaded && thumb.image) {
          ctx.drawImage(thumb.image, x, stripY + 4, THUMB_SIZE, THUMB_SIZE);
        } else {
          ctx.fillStyle = "#333";
          ctx.fillRect(x, stripY + 4, THUMB_SIZE, THUMB_SIZE);
          ctx.fillStyle = "#666";
          ctx.textAlign = "center";
          ctx.font = "10px monospace";
          ctx.fillText("...", x + THUMB_SIZE / 2, stripY + 4 + THUMB_SIZE / 2 + 3);
        }
        ctx.fillStyle = "rgba(0,0,0,0.6)";
        ctx.fillRect(x, stripY + 4 + THUMB_SIZE - 14, THUMB_SIZE, 14);
        ctx.fillStyle = "#ccc";
        ctx.textAlign = "center";
        ctx.font = "10px monospace";
        ctx.fillText(
          `#${thumb.iteration}`,
          x + THUMB_SIZE / 2,
          stripY + 4 + THUMB_SIZE - 3
        );
      }
      ctx.restore();
    };
    const origOnMouseDown = nodeType.prototype.onMouseDown;
    nodeType.prototype.onMouseDown = function(e, pos, canvas) {
      var _a;
      const thumbIdx = this._hitTestThumb(pos);
      if (thumbIdx >= 0) {
        const thumb = this._thumbs[thumbIdx];
        if (e.button === 2) {
          e.preventDefault();
          this._showThumbContextMenu(e, thumb);
          return true;
        }
        this._pinnedIteration = thumb.iteration;
        const pinWidget = (_a = this.widgets) == null ? void 0 : _a.find((w) => w.name === "pin_index");
        if (pinWidget) pinWidget.value = thumb.iteration;
        this.setDirtyCanvas(true, false);
        return true;
      }
      return origOnMouseDown == null ? void 0 : origOnMouseDown.apply(this, arguments);
    };
    nodeType.prototype._hitTestThumb = function(pos) {
      if (!this._thumbs.length || !this._contactSheetWidget) return -1;
      const widgetY = this._contactSheetWidget.last_y || 0;
      const stripY = widgetY + 4;
      const startX = 14 - this._stripScrollX;
      for (let i = 0; i < this._thumbs.length; i++) {
        const x = startX + i * (THUMB_SIZE + THUMB_GAP);
        if (pos[0] >= x && pos[0] <= x + THUMB_SIZE && pos[1] >= stripY + 4 && pos[1] <= stripY + 4 + THUMB_SIZE) {
          return i;
        }
      }
      return -1;
    };
    nodeType.prototype._showThumbContextMenu = function(e, thumb) {
      new LiteGraph.ContextMenu(
        [
          {
            title: `Pin iteration #${thumb.iteration}`,
            callback: () => {
              var _a;
              this._pinnedIteration = thumb.iteration;
              const pinWidget = (_a = this.widgets) == null ? void 0 : _a.find((w) => w.name === "pin_index");
              if (pinWidget) pinWidget.value = thumb.iteration;
              this.setDirtyCanvas(true, false);
            }
          },
          {
            title: "Unpin",
            callback: () => {
              var _a;
              this._pinnedIteration = 0;
              const pinWidget = (_a = this.widgets) == null ? void 0 : _a.find((w) => w.name === "pin_index");
              if (pinWidget) pinWidget.value = 0;
              this.setDirtyCanvas(true, false);
            }
          },
          null,
          {
            title: "Open in preview",
            callback: () => {
              const params = new URLSearchParams({
                filename: thumb.filename,
                subfolder: thumb.subfolder,
                type: thumb.type
              });
              window.open(api.apiURL(`/view?${params.toString()}`), "_blank");
            }
          }
        ],
        { event: e, scale: 1 }
      );
    };
  }
});
