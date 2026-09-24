const COLORS = ["#1769aa", "#c44d00", "#2e7d32", "#7b1fa2"];
const INSET = 8;
const BLOCK_SIZE = 64;
const summaries = new WeakMap();

function sampleCount(chunk) {
  return chunk.time_s?.length ?? Object.values(chunk.channels || {})[0]?.values?.length ?? 0;
}

function summaryFor(values) {
  let summary = summaries.get(values);
  if (summary) return summary;
  const blocks = [];
  let minY = Infinity;
  let maxY = -Infinity;
  for (let start = 0; start < values.length; start += BLOCK_SIZE) {
    let min = -1;
    let max = -1;
    for (let index = start; index < Math.min(start + BLOCK_SIZE, values.length); index += 1) {
      if (!Number.isFinite(values[index])) continue;
      if (min < 0 || values[index] < values[min]) min = index;
      if (max < 0 || values[index] > values[max]) max = index;
    }
    blocks.push({ min, max });
    if (min >= 0) minY = Math.min(minY, values[min]);
    if (max >= 0) maxY = Math.max(maxY, values[max]);
  }
  summary = { blocks, minY, maxY };
  summaries.set(values, summary);
  return summary;
}

function extremaInRange(values, blocks, start, end) {
  let min = -1;
  let max = -1;
  const add = (index) => {
    if (index < 0 || !Number.isFinite(values[index])) return;
    if (min < 0 || values[index] < values[min]) min = index;
    if (max < 0 || values[index] > values[max]) max = index;
  };
  for (let index = start; index <= end;) {
    if (index % BLOCK_SIZE === 0 && index + BLOCK_SIZE - 1 <= end) {
      const block = blocks[index / BLOCK_SIZE];
      add(block.min);
      add(block.max);
      index += BLOCK_SIZE;
    } else {
      add(index);
      index += 1;
    }
  }
  return { min, max };
}

export function lookupMonitorSample(chunks, globalIndex) {
  for (const chunk of chunks) {
    const localIndex = globalIndex - chunk.global_start_index;
    if (localIndex < 0 || localIndex >= sampleCount(chunk)) continue;
    return {
      captureIndex: chunk.capture_index,
      globalIndex,
      localIndex,
      time: chunk.time_s?.[localIndex],
      channels: Object.fromEntries(Object.entries(chunk.channels || {}).map(
        ([name, data]) => [name, { value: data.values[localIndex], unit: data.unit || "" }],
      )),
    };
  }
  return null;
}

export function projectMonitorChunks(chunks, pixelWidth) {
  const retained = chunks.filter((chunk) => sampleCount(chunk) > 0);
  if (!retained.length) return null;
  const minX = retained[0].global_start_index;
  const last = retained[retained.length - 1];
  const maxX = last.global_start_index + sampleCount(last) - 1;
  const bucketCount = Math.max(1, Math.floor(pixelWidth));
  const span = Math.max(1, maxX - minX);
  const channels = new Map();
  let minY = Infinity;
  let maxY = -Infinity;

  for (const chunk of retained) {
    for (const [name, data] of Object.entries(chunk.channels || {})) {
      if (!channels.has(name)) channels.set(name, []);
      const count = Math.min(sampleCount(chunk), data.values.length);
      if (!count) continue;
      const summary = summaryFor(data.values);
      minY = Math.min(minY, summary.minY);
      maxY = Math.max(maxY, summary.maxY);
      const segment = [];
      const firstBucket = Math.min(bucketCount - 1, Math.floor(
        ((chunk.global_start_index - minX) / span) * bucketCount,
      ));
      const lastBucket = Math.min(bucketCount - 1, Math.floor(
        ((chunk.global_start_index + count - 1 - minX) / span) * bucketCount,
      ));
      for (let bucket = firstBucket; bucket <= lastBucket; bucket += 1) {
        const start = Math.max(0, minX + Math.ceil((bucket * span) / bucketCount) - chunk.global_start_index);
        const end = Math.min(count - 1, (
          bucket === bucketCount - 1 ? maxX : minX + Math.ceil(((bucket + 1) * span) / bucketCount) - 1
        ) - chunk.global_start_index);
        if (start > end) continue;
        const extremes = extremaInRange(data.values, summary.blocks, start, end);
        if (extremes.min < 0) continue;
        const indices = [...new Set([start, extremes.min, extremes.max, end])].sort((a, b) => a - b);
        for (const index of indices) {
          segment.push([chunk.global_start_index + index, data.values[index]]);
        }
      }
      if (segment.length) channels.get(name).push(segment);
    }
  }
  return { minX, maxX, minY, maxY, channels };
}

export class MonitorChart {
  constructor(canvas, crosshair, tooltip, getChunks, translate) {
    this.canvas = canvas;
    this.crosshair = crosshair;
    this.tooltip = tooltip;
    this.getChunks = getChunks;
    this.translate = translate;
    this.onMove = (event) => {
      this.pointerX = event.clientX;
      this.showHover(this.pointerX);
    };
    this.onLeave = () => {
      this.pointerX = undefined;
      this.hideHover();
    };
    canvas.addEventListener("mousemove", this.onMove);
    canvas.addEventListener("mouseleave", this.onLeave);
    if (typeof ResizeObserver !== "undefined") {
      this.resizeObserver = new ResizeObserver(() => this.requestDraw());
      this.resizeObserver.observe(canvas);
    }
    this.requestDraw();
  }

  dispose() {
    this.resizeObserver?.disconnect();
    this.canvas.removeEventListener?.("mousemove", this.onMove);
    this.canvas.removeEventListener?.("mouseleave", this.onLeave);
    if (this.frame !== undefined && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(this.frame);
    }
    this.disposed = true;
  }

  requestDraw() {
    if (this.frame !== undefined || this.disposed) return;
    const schedule = globalThis.requestAnimationFrame || ((callback) => queueMicrotask(callback));
    this.frame = schedule(() => {
      this.frame = undefined;
      if (!this.disposed) this.draw();
    });
  }

  draw() {
    const context = this.canvas.getContext?.("2d");
    if (!context) return;
    const rect = this.canvas.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    if (!width || !height) return;
    const ratio = globalThis.devicePixelRatio || 1;
    const bitmapWidth = Math.round(width * ratio);
    const bitmapHeight = Math.round(height * ratio);
    if (this.canvas.width !== bitmapWidth) this.canvas.width = bitmapWidth;
    if (this.canvas.height !== bitmapHeight) this.canvas.height = bitmapHeight;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    const plotWidth = Math.max(1, width - INSET * 2);
    const projection = projectMonitorChunks(this.getChunks(), plotWidth);
    this.projection = projection;
    if (!projection || !Number.isFinite(projection.minY)) {
      this.hideHover();
      return;
    }
    let colorIndex = 0;
    for (const segments of projection.channels.values()) {
      context.strokeStyle = COLORS[colorIndex++ % COLORS.length];
      for (const segment of segments) {
        context.beginPath();
        segment.forEach(([x, y], index) => {
          const px = INSET + ((x - projection.minX) / Math.max(1, projection.maxX - projection.minX)) * plotWidth;
          const py = height - INSET - ((y - projection.minY) / Math.max(1e-12, projection.maxY - projection.minY)) * (height - INSET * 2);
          if (index === 0) context.moveTo(px, py); else context.lineTo(px, py);
        });
        context.stroke();
      }
    }
    if (this.pointerX === undefined) this.hideHover();
    else this.showHover(this.pointerX);
  }

  showHover(clientX) {
    const projection = this.projection;
    if (!projection) return this.hideHover();
    const rect = this.canvas.getBoundingClientRect();
    const fraction = Math.max(0, Math.min(1, (clientX - rect.left - INSET) / Math.max(1, rect.width - INSET * 2)));
    const index = Math.round(projection.minX + fraction * (projection.maxX - projection.minX));
    const sample = lookupMonitorSample(this.getChunks(), index);
    if (!sample) return this.hideHover();
    const formatted = (value) => Number.isFinite(value) ? String(Number(value.toPrecision(6))) : String(value);
    const lines = [
      this.translate("workflow.monitor.hoverCapture", { value: sample.captureIndex }),
      this.translate("workflow.monitor.hoverGlobal", { value: sample.globalIndex }),
      this.translate("workflow.monitor.hoverSample", { value: sample.localIndex }),
      this.translate("workflow.monitor.hoverTime", { value: formatted(sample.time) }),
      ...Object.entries(sample.channels).map(([name, data]) => `${name}: ${formatted(data.value)} ${data.unit}`.trim()),
    ];
    this.tooltip.textContent = lines.join("\n");
    this.tooltip.hidden = false;
    this.crosshair.hidden = false;
    const x = INSET + ((sample.globalIndex - projection.minX) / Math.max(1, projection.maxX - projection.minX)) * (rect.width - INSET * 2);
    this.crosshair.style.left = `${x}px`;
    this.tooltip.style.left = `${Math.min(x + 10, Math.max(0, rect.width - this.tooltip.offsetWidth - 8))}px`;
  }

  hideHover() {
    this.crosshair.hidden = true;
    this.tooltip.hidden = true;
  }
}
