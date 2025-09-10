// Seeded, path-aware, collision-free layout
export type XYPct = { x: number; y: number };

function hash32(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}
function hash01(s: string) { return (hash32(s) % 1_000_000) / 1_000_000; }

// Halton (van der Corput) bases 2 and 3 for blue-noise-ish jitter
function vdc(n: number, base: number) {
  let v = 0, denom = 1;
  while (n > 0) {
    denom *= base;
    v += (n % base) / denom;
    n = Math.floor(n / base);
  }
  return v;
}
function halton(idx: number, base: 2 | 3) { return vdc(idx + 1, base); }

// px -> % helpers
function pxToPctX(px: number, graphW: number) { return (px / Math.max(1, graphW)) * 100; }
function pxToPctY(px: number, graphH: number) { return (px / Math.max(1, graphH)) * 100; }

export function calculateNodePositions(
  toolMetadata: Array<Record<string, unknown>>,
  paths: string[][],
  graphW: number,
  graphH: number,
  existing: Record<string, XYPct> = {},
  minCenterDistancePx = 100,
  borderPadPx = 30,
  seed?: number
): Record<string, XYPct> {
  // ---- Normalize inputs defensively
  const meta = Array.isArray(toolMetadata) ? toolMetadata : [];
  const safePaths: string[][] = Array.isArray(paths) ? paths.filter(p => Array.isArray(p)) : [];
  const pos: Record<string, XYPct> = { ...existing };

  // ---- Endpoints pinned left/right (support generic INPUT/OUTPUT fallbacks too)
  const startNodes = ["IMAGE_IN", "IMG", "INPUT"];
  const endNodes = ["IMAGE_OUT", "IMG", "OUTPUT"];

  const leftMarginPx = 60, rightMarginPx = 60;
  const xLeftPct = Math.max(0, Math.min(100, pxToPctX(leftMarginPx, graphW)));
  const xRightPct = Math.max(0, Math.min(100, 100 - pxToPctX(rightMarginPx, graphW)));

  // Pin both endpoints on the same Y-level for cleaner layout
  const endpointY = 50;
  for (const s of startNodes) pos[s] = { x: xLeftPct, y: pos[s]?.y ?? endpointY };
  for (const e of endNodes) if (!startNodes.includes(e)) pos[e] = { x: xRightPct, y: pos[e]?.y ?? endpointY };

  // ---- Collect node set (exclude endpoints) from paths + metadata
  const metaNames = new Set<string>();
  for (const t of meta) {
    const n = (t?.name as string) || "";
    if (n && !startNodes.includes(n) && !endNodes.includes(n)) metaNames.add(n);
  }
  const midNodes = new Set<string>();
  for (const p of safePaths) for (const n of p) {
    if (!startNodes.includes(n) && !endNodes.includes(n)) midNodes.add(n);
  }
  for (const n of metaNames) midNodes.add(n);

  if (midNodes.size === 0) {
    clampAll(pos, graphW, graphH, borderPadPx, xLeftPct, xRightPct, startNodes, endNodes);
    return pos;
  }

  // ---- Path statistics for relative stage & left-bias
  const totalPaths = safePaths.length || 1;
  const stat = new Map<string, { stageSum: number; stageCnt: number; firstCnt: number; presentCnt: number }>();
  for (const n of midNodes) stat.set(n, { stageSum: 0, stageCnt: 0, firstCnt: 0, presentCnt: 0 });

  for (const p of safePaths) {
    if (p.length < 2) continue;
    const inner = p.slice(1, -1).filter(n => !startNodes.includes(n) && !endNodes.includes(n));
    if (inner.length) {
      const first = inner[0];
      if (stat.has(first)) stat.get(first)!.firstCnt += 1;

      const denom = Math.max(1, inner.length - 1);
      inner.forEach((n, i) => {
        const s = stat.get(n); if (!s) return;
        s.stageSum += (i / denom); // 0..1
        s.stageCnt += 1;
      });
    }
    // Presence per path
    const uniq = new Set(inner);
    for (const n of uniq) stat.get(n)!.presentCnt += 1;
  }

  // ---- Column planning
  const N = midNodes.size;
  const numCols = Math.max(3, Math.min(9, Math.round(Math.sqrt(N)) + 2)); // 3..9 columns
  const leftX = 12, rightX = 88; // keep gutters
  const colXs: number[] = [];
  for (let c = 0; c < numCols; c++) {
    const t = numCols === 1 ? 0.5 : c / (numCols - 1);
    colXs.push(leftX + t * (rightX - leftX));
  }

  const FIRST_LEFT_BIAS = 0.65;  // stronger pull left if often first
  const PRESENCE_SQUEEZE = 0.20; // frequent nodes have less lateral drift

  type Plan = { id: string; col: number; baseX: number; jx: number; jy: number; biasedStage: number; presence: number };
  const plans: Plan[] = [];
  let idx = 0;
  for (const id of midNodes) {
    const s = stat.get(id)!;
    const avgStage = s.stageCnt ? s.stageSum / s.stageCnt : 0.5;      // 0..1
    const firstRatio = s.firstCnt / totalPaths;                        // 0..1
    const presence = s.presentCnt / totalPaths;                        // 0..1

    // Pull to left by how often it's first
    const biasedStage = avgStage * (1 - FIRST_LEFT_BIAS * firstRatio); // smaller => more left
    const col = Math.max(0, Math.min(numCols - 1, Math.round(biasedStage * (numCols - 1))));
    const colX = colXs[col];

    const nodeSeed = (seed ?? 0) ^ hash32(id);
    const jx = (halton(idx + (nodeSeed % 997), 2) - 0.5); // -0.5..0.5
    const jy = (halton(idx + (nodeSeed % 991), 3) - 0.5);

    // Presence squeezes lateral drift: more common => stay nearer column center
    const lateralScale = (1 - PRESENCE_SQUEEZE * presence) * 0.7;
    const baseX = colX + jx * lateralScale * 6; // small lateral (in %)

    plans.push({ id, col, baseX, jx, jy, biasedStage, presence });
    idx++;
  }

  // ---- Vertical packing per column (even spacing + deterministic jitter)
  const minXDistPct = pxToPctX(minCenterDistancePx, graphW);
  const minYDistPct = pxToPctY(minCenterDistancePx, graphH);

  const colBuckets: Map<number, Plan[]> = new Map();
  for (const p of plans) {
    if (!colBuckets.has(p.col)) colBuckets.set(p.col, []);
    colBuckets.get(p.col)!.push(p);
  }

  const topY = 15, botY = 85;
  for (const [col, arr] of colBuckets) {
    // Deterministic seed order for stability
    arr.sort((a, b) => {
      const ha = hash32(a.id + "|" + (seed ?? 0));
      const hb = hash32(b.id + "|" + (seed ?? 0));
      return ha - hb || a.id.localeCompare(b.id);
    });
    const n = arr.length;
    if (!n) continue;

    const band = botY - topY;
    const step = Math.max(minYDistPct, band / (n + 1));
    let y = topY + step;

    for (let i = 0; i < n; i++) {
      const p = arr[i];
      const jitter = (p.jy * 0.8) * Math.min(step * 0.45, 4); // up to ~45% of step, capped
      const yy = Math.max(topY, Math.min(botY, y + jitter));
      if (!existing[p.id]) pos[p.id] = { x: p.baseX, y: yy }; // respect pre-placed
      y += step;
    }
  }

  // Ensure endpoints exist
  for (const s of startNodes) pos[s] = pos[s] ?? { x: xLeftPct, y: endpointY };
  for (const e of endNodes) pos[e] = pos[e] ?? { x: xRightPct, y: endpointY };

  // ---- Collision resolution (grid-based separation; respects pre-placed + endpoint X pinning)
  separateNoOverlap(pos, {
    startNodes, endNodes,
    fixed: new Set(Object.keys(existing || {})),
    xPadPct: Math.max(minXDistPct, 4),
    yPadPct: Math.max(minYDistPct, 3),
    borderPadPctX: pxToPctX(borderPadPx, graphW),
    borderPadPctY: pxToPctY(borderPadPx, graphH),
    xLeftPct, xRightPct,
    iterations: 6
  });

  // ---- Final clamp
  clampAll(pos, graphW, graphH, borderPadPx, xLeftPct, xRightPct, startNodes, endNodes);
  return pos;
}

// ---------- Helpers ----------

function clampAll(
  pos: Record<string, XYPct>,
  graphW: number,
  graphH: number,
  borderPadPx: number,
  xLeftPct: number,
  xRightPct: number,
  startNodes: string[],
  endNodes: string[],
) {
  const padX = pxToPctX(borderPadPx, graphW);
  const padY = pxToPctY(borderPadPx, graphH);
  for (const k of Object.keys(pos)) {
    const isStart = startNodes.includes(k);
    const isEnd = endNodes.includes(k) && !isStart;
    if (isStart) pos[k].x = xLeftPct;
    else if (isEnd) pos[k].x = xRightPct;
    else pos[k].x = Math.max(padX, Math.min(100 - padX, pos[k].x));
    pos[k].y = Math.max(padY, Math.min(100 - padY, pos[k].y));
  }
}

function separateNoOverlap(
  pos: Record<string, XYPct>,
  opts: {
    startNodes: string[];
    endNodes: string[];
    fixed: Set<string>;
    xPadPct: number;
    yPadPct: number;
    borderPadPctX: number;
    borderPadPctY: number;
    xLeftPct: number;
    xRightPct: number;
    iterations: number;
  }
) {
  const keys = Object.keys(pos);
  const { startNodes, endNodes, fixed, xPadPct, yPadPct, borderPadPctX, borderPadPctY, xLeftPct, xRightPct } = opts;

  // Use a spatial grid to keep it fast
  const cellW = xPadPct, cellH = yPadPct;

  for (let it = 0; it < opts.iterations; it++) {
    const grid = new Map<string, string[]>();
    const keyFor = (x: number, y: number) => `${Math.floor(x / cellW)},${Math.floor(y / cellH)}`;

    for (const id of keys) {
      const p = pos[id];
      const k = keyFor(p.x, p.y);
      if (!grid.has(k)) grid.set(k, []);
      grid.get(k)!.push(id);
    }

    let moved = false;
    for (const id of keys) {
      const a = pos[id];
      const aIsStart = startNodes.includes(id);
      const aIsEnd = endNodes.includes(id) && !aIsStart;
      const aIsFixed = fixed.has(id);

      const cx = Math.floor(a.x / cellW);
      const cy = Math.floor(a.y / cellH);

      for (let oy = -1; oy <= 1; oy++) {
        for (let ox = -1; ox <= 1; ox++) {
          const bucket = grid.get(`${cx + ox},${cy + oy}`);
          if (!bucket) continue;

          for (const other of bucket) {
            if (other === id) continue;
            const b = pos[other];
            const dx = a.x - b.x;
            const dy = a.y - b.y;

            const overlapX = xPadPct - Math.abs(dx);
            const overlapY = yPadPct - Math.abs(dy);
            if (overlapX > 0 && overlapY > 0) {
              if (aIsFixed) continue; // don't move fixed nodes

              moved = true;
              if (overlapX > overlapY) {
                // separate along x
                const push = Math.sign(dx || (Math.random() - 0.5)) * overlapX * 0.55;
                if (!aIsStart && !aIsEnd) a.x += push; // endpoints' X stays pinned
              } else {
                // separate along y
                const push = Math.sign(dy || (Math.random() - 0.5)) * overlapY * 0.55;
                a.y += push; // endpoints may move vertically
              }

              // Clamp + re-pin endpoints’ X
              a.x = Math.max(borderPadPctX, Math.min(100 - borderPadPctX, a.x));
              a.y = Math.max(borderPadPctY, Math.min(100 - borderPadPctY, a.y));
              if (aIsStart) a.x = xLeftPct;
              if (aIsEnd) a.x = xRightPct;
            }
          }
        }
      }
    }
    if (!moved) break;
  }
}
