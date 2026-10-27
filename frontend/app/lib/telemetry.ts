// Client-side Hardware, Device Fingerprint and Engagement Telemetry

export interface DeviceTelemetry {
  screen_resolution: string;
  viewport_size: string;
  pixel_ratio: number;
  cpu_cores: number | null;
  ram_gb_approx: number | null;
  gpu_renderer: string | null;
  platform: string;
  timezone: string;
  languages: string[];
  touch_points: number;
  dwell_time_seconds?: number;
  max_scroll_depth?: number;
}

/**
 * Generates a fast, deterministic canvas fingerprint hash.
 */
export function getCanvasFingerprint(): string {
  if (typeof window === "undefined") return "server";
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 240;
    canvas.height = 60;
    const ctx = canvas.getContext("2d");
    if (!ctx) return "no_canvas";

    ctx.textBaseline = "top";
    ctx.font = "14px 'Arial', sans-serif";
    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = "#f60";
    ctx.fillRect(125, 1, 62, 20);
    ctx.fillStyle = "#069";
    ctx.fillText("interactive-cv,telemetry-probe", 2, 15);
    ctx.fillStyle = "rgba(102, 204, 0, 0.7)";
    ctx.fillText("interactive-cv,telemetry-probe", 4, 17);

    const b64 = canvas.toDataURL();
    // Simple fast 32-bit FNV-1a hash
    let hash = 2166136261;
    for (let i = 0; i < b64.length; i++) {
      hash ^= b64.charCodeAt(i);
      hash += (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24);
    }
    return (hash >>> 0).toString(16);
  } catch {
    return "unknown";
  }
}

/**
 * Extracts GPU model via WebGL debug renderer info.
 */
function getGpuRenderer(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl") || (canvas.getContext("experimental-webgl") as WebGLRenderingContext);
    if (!gl) return null;
    const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
    if (!debugInfo) return null;
    return gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) || null;
  } catch {
    return null;
  }
}

/**
 * Collects hardware, display, and localization metrics.
 */
export function collectDeviceTelemetry(dwellSeconds?: number, scrollDepth?: number): {
  fingerprint: string;
  metadata: DeviceTelemetry;
} {
  if (typeof window === "undefined") {
    return {
      fingerprint: "server",
      metadata: {
        screen_resolution: "unknown",
        viewport_size: "unknown",
        pixel_ratio: 1,
        cpu_cores: null,
        ram_gb_approx: null,
        gpu_renderer: null,
        platform: "unknown",
        timezone: "UTC",
        languages: [],
        touch_points: 0
      }
    };
  }

  const nav = navigator as any;
  const metadata: DeviceTelemetry = {
    screen_resolution: `${window.screen?.width || 0}x${window.screen?.height || 0}`,
    viewport_size: `${window.innerWidth}x${window.innerHeight}`,
    pixel_ratio: window.devicePixelRatio || 1,
    cpu_cores: nav.hardwareConcurrency || null,
    ram_gb_approx: nav.deviceMemory || null,
    gpu_renderer: getGpuRenderer(),
    platform: nav.platform || "unknown",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "unknown",
    languages: nav.languages ? [...nav.languages] : [nav.language || "unknown"],
    touch_points: nav.maxTouchPoints || 0,
    dwell_time_seconds: dwellSeconds,
    max_scroll_depth: scrollDepth
  };

  return {
    fingerprint: getCanvasFingerprint(),
    metadata
  };
}
