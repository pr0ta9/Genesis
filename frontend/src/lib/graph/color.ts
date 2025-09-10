// Deterministic color generation for a token (stable across sessions)
// Inspired by gui/utils/color.py

function hashStringMD5Like(input: string, seed?: number): number {
  // Lightweight non-cryptographic hash (doesn't need real MD5 for stability)
  let h = seed || 0;
  for (let i = 0; i < input.length; i++) {
    h = (h * 131 + input.charCodeAt(i)) >>> 0;
  }
  return h >>> 0;
}

function hslToHex(h: number, s: number, l: number): string {
  // h,s,l in [0,1]
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => {
    const k = (n + h * 12) % 12;
    const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * color)
      .toString(16)
      .padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

export function colorForToken(token: string, satRange: [number, number] = [0.6, 0.75], ligRange: [number, number] = [0.45, 0.6], seed?: number): string {
  const h = hashStringMD5Like(token, seed);
  const hue = (h % 360) / 360; // [0,1)
  const s = satRange[0] + ((h >>> 8) % 1000) / 1000 * (satRange[1] - satRange[0]);
  const l = ligRange[0] + ((h >>> 16) % 1000) / 1000 * (ligRange[1] - ligRange[0]);
  return hslToHex(hue, s, l);
}

export function ensureColors(tokens: string[], existing: Record<string, string> = {}, seed?: number): Record<string, string> {
  const out: Record<string, string> = { ...existing };
  for (const t of tokens) {
    if (!out[t]) {
      // Fixed colors for start/end nodes
      if (t === "IMAGE_IN" || t === "IMG" || t === "INPUT") {
        out[t] = "#dbeafe"; // Light blue for input nodes
      } else if (t === "IMAGE_OUT") {
        out[t] = "#dcfce7"; // Light green for output nodes
      } else if (t === "OUTPUT") {
        // When falling back to generic OUTPUT, match input node color for visual consistency
        out[t] = "#dbeafe";
      } else {
        out[t] = colorForToken(t, [0.6, 0.75], [0.45, 0.6], seed);
      }
    }
  }
  return out;
}


