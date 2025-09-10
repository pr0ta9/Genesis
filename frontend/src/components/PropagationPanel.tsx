"use client";
import React, { useMemo } from "react";
import Propagation from "./Propagation";
import pipeline from "./pipeline";
import { useApp } from "@/lib/state/AppContext";

export function PropagationPanel() {
  const { latestState, graph } = useApp();

  const progressPct = useMemo(() => {
    // Derive progress from latest state if available; fallback to 0
    try {
      const path = (latestState as any)?.chosen_path as Array<any> | undefined;
      const step = (latestState as any)?.current_step as number | undefined;
      if (path && path.length && typeof step === "number") {
        const total = path.length + 1; // include IMAGE_OUT
        return Math.min(100, Math.max(0, Math.round(((step + 1) / total) * 100)));
      }
    } catch {}
    return 0;
  }, [latestState]);

  const hasGraph = ((graph?.currentPaths?.length || 0) > 0) || ((graph?.chosenPath && graph.chosenPath.length) ? 1 : 0) || ((graph?.allPaths?.length || 0) > 0);
  if (!hasGraph) {
    return (
      <div className="h-full w-full bg-white flex items-center justify-center text-sm text-gray-500">
        No path data yet. Waiting for find_path...
      </div>
    );
  }

  return (
    <div className="h-full w-full bg-white flex flex-col overflow-hidden">
      <div className="p-4 flex-1 min-h-0 flex flex-col">
        <div className="grid grid-cols-12 gap-4 h-full">
          <div className="col-span-12 xl:col-span-8 flex flex-col min-h-0">
            <div className="pb-2 px-1 flex-none">
              <h3 className="text-base font-semibold text-gray-900">Propagation</h3>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <Propagation />
            </div>
          </div>
          <div className="col-span-12 xl:col-span-4 flex flex-col min-h-0">
            <div className="pb-2 px-1 flex-none">
              <h3 className="text-base font-semibold text-gray-900">Pipeline</h3>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              {pipeline({ progress: progressPct })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}