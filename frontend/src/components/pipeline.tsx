"use client";
import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useApp } from "@/lib/state/AppContext";

export default function Pipeline({ progress }: { progress: number }) {
  const { graph, currentToolName, currentStepIndex, stage, dispatch } = useApp();
  const pct = Math.min(100, Math.max(0, progress));

  // Shared animation state
  const anim = graph.animation;
  const hasChosenPath = !!(graph.chosenPath && graph.chosenPath.length > 0);
  const mode = anim?.mode || (hasChosenPath && graph.reduceAnimationCompleted ? 'chosen_path' : 'find_path');
  console.log('[Pipeline] Mode', mode);
  const populateIndex = anim?.populate.currentIndex ?? (hasChosenPath ? 0 : graph.allPaths.length);
  const populateCompleted = anim?.populate.completed ?? false;
  const reduceIndex = anim?.reduce.currentIndex ?? 0;
  const reduceStarted = anim?.reduce.started ?? false;

  // Debug selection/animation state
  try {
    console.log('[Pipeline] Render', {
      mode,
      populateIndex,
      populateCompleted,
      reduceIndex,
      reduceStarted,
      hasChosenPath,
      reduceAnimationCompleted: graph.reduceAnimationCompleted,
      allPathsCount: graph.allPaths.length,
    });
  } catch {}

  // Determine visible paths from UI-ephemeral currentPaths if present
  const visiblePaths: string[][] = (graph.currentPaths && graph.currentPaths.length)
    ? graph.currentPaths
    : (hasChosenPath && graph.chosenPath ? [graph.chosenPath] : graph.allPaths);

  // Title logic: depend on what we actually render
  const isSelectedView = hasChosenPath && visiblePaths.length === 1 && JSON.stringify(visiblePaths[0]) === JSON.stringify(graph.chosenPath);
  const title = isSelectedView ? "Selected path" : "Available paths";

  if (!visiblePaths.length) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-4 h-full grid place-items-center text-sm text-slate-500">
        Waiting for available paths...
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 h-full">
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <h3 className="text-base font-semibold text-gray-900">{title}</h3>
      </div>

      <div className="mt-4 space-y-3 max-h-[calc(100%-4rem)] overflow-y-auto">
        <AnimatePresence mode="popLayout">
        {visiblePaths.map((path, index) => {
          if (!path) return null;
          const isChosen = hasChosenPath && graph.chosenPath && JSON.stringify(path) === JSON.stringify(graph.chosenPath);
          const isSelected = mode === 'chosen_path' ? true : isChosen || index === 0;
          const globalIndex = graph.allPaths.findIndex(p => JSON.stringify(p) === JSON.stringify(path));
          const isBeingAdded = mode === 'find_path' && globalIndex === populateIndex;
          const isBeingEliminated = mode === 'reduce' && reduceStarted && globalIndex === reduceIndex;

          // Determine currently executing node within this path, or output node during finalize
          const executingNode = (() => {
            if (stage === 'finalize') {
              // Prefer last token in chosenPath as output display
              if (hasChosenPath && graph.chosenPath && graph.chosenPath.length > 0) {
                return graph.chosenPath[graph.chosenPath.length - 1];
              }
            }
            if (currentToolName && typeof currentToolName === 'string') return currentToolName;
            if (typeof currentStepIndex === 'number' && hasChosenPath && graph.chosenPath && currentStepIndex >= 0 && currentStepIndex < graph.chosenPath.length) {
              return graph.chosenPath[currentStepIndex];
            }
            return undefined;
          })();

          // Per-path debug
          try {
            console.log('[Pipeline] Path entry', {
              globalIndex,
              renderIndex: index,
              isChosen,
              isSelected,
              isBeingAdded,
              isBeingEliminated,
              path,
            });
          } catch {}
          
          return (
            <motion.div
              key={JSON.stringify(path)}
              className={`p-3 rounded-lg border transition-all duration-200 cursor-pointer hover:shadow-sm ${
                isBeingEliminated
                  ? "border-red-400 bg-red-100 shadow-md"
                  : isBeingAdded
                  ? "border-green-300 bg-green-50 shadow-sm"
                  : isSelected
                  ? "border-blue-200 bg-blue-50 shadow-sm"
                  : "border-gray-200 bg-white hover:border-gray-300"
              }`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ delay: index * 0.05 }}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div
                    className={`flex items-center gap-2 mb-3 ${
                      isSelected ? "text-blue-900" : "text-gray-900"
                    }`}
                  >
                    <div
                      className={`flex items-center justify-center w-6 h-6 rounded-full text-xs font-semibold ${
                        isSelected ? "bg-blue-600 text-white" : "bg-gray-600 text-white"
                      }`}
                    >
                      {index + 1}
                    </div>
                    <div className="text-sm font-medium">Path {globalIndex + 1}</div>
                    <div className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
                      {path.length} step{path.length === 1 ? "" : "s"}
                    </div>
                  </div>

                  {/* Visual Path Flow */}
                  <div className="flex flex-wrap items-center gap-2 leading-relaxed">
                    {path.map((step: string, stepIndex: number) => {
                      const isEdgeNode =
                        stepIndex === 0 || stepIndex === path.length - 1;
                      const isExecuting = executingNode === step && !isEdgeNode;

                      const bg = isEdgeNode
                        ? "#CBDCEB"
                        : isBeingEliminated
                        ? `linear-gradient(135deg, #fecaca, #f87171)` // Red gradient for elimination
                        : isBeingAdded
                        ? `linear-gradient(135deg, #dcfce7, #86efac)`
                        : isSelected
                        ? `linear-gradient(135deg, ${
                            graph.colors?.[step] || "#dbeafe"
                          }, ${
                            graph.colors?.[step]
                              ? graph.colors[step] + "CC"
                              : "#bfdbfe"
                          })`
                        : `linear-gradient(135deg, ${
                            graph.colors?.[step] || "#f8fafc"
                          }, ${
                            graph.colors?.[step]
                              ? graph.colors[step] + "80"
                              : "#e2e8f0"
                          })`;

                      return (
                        <React.Fragment key={stepIndex}>
                          <motion.div
                            className={`group relative ${
                              stepIndex > 0 ? "ml-1" : ""
                            }`}
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: isExecuting ? 1.06 : 1 }}
                            transition={{
                              delay: index * 0.05 + stepIndex * 0.1,
                            }}
                          >
                            <span
                              className={[
                                "inline-flex items-center rounded-lg text-xs font-medium",
                                "transition-all duration-150",
                                // kill any tailwind borders/rings/outlines/hover shadows
                                "!border-0 !ring-0 !outline-none focus:!outline-none focus:!ring-0",
                                "hover:shadow-none"
                              ].join(" ")}
                              style={{
                                background: bg,
                                padding: isExecuting ? "10px 14px" : "8px 12px",
                                cursor: "pointer",
                                // hard-disable any UA borders/outlines/shadows
                                border: 0,
                                outline: "none",
                                boxShadow: isExecuting ? "0 0 0 2px rgba(99,102,241,0.35)" : "none",
                                WebkitTapHighlightColor: "transparent" // avoid tap highlight on mobile
                              }}
                              onClick={() => {
                                let mappedIndex = stepIndex;
                                if (graph.chosenPath && graph.chosenPath.length) {
                                  const idx = graph.chosenPath.findIndex((n) => n === step);
                                  if (idx >= 0) mappedIndex = idx;
                                }
                                dispatch({ type: "select_execution_step", tool_name: step, step_index: mappedIndex });
                              }}
                            >
                              <span className={`relative z-10 ${isExecuting ? "font-semibold text-indigo-900" : ""}`}>
                                {step}
                              </span>
                            </span>
                          </motion.div>

                          {stepIndex < path.length - 1 && (
                            <div className="flex items-center">
                              <motion.div
                                className={`flex items-center ${
                                  isBeingEliminated
                                    ? "text-red-500"
                                    : isBeingAdded
                                    ? "text-green-500"
                                    : isSelected 
                                    ? "text-blue-400" 
                                    : "text-gray-400"
                                }`}
                                initial={{ opacity: 0, x: -5 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{
                                  delay:
                                    index * 0.05 + stepIndex * 0.1 + 0.05,
                                }}
                              >
                                <svg
                                  className="w-4 h-4"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 5l7 7-7 7"
                                  />
                                </svg>
                              </motion.div>
                            </div>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </div>
                </div>
              </div>
              {isSelected && (
                <div className="mt-3 pt-2 border-t border-blue-100">
                  <div className="flex items-center justify-between text-xs text-blue-700 mb-1">
                    <span>Progress</span>
                    <span>{Math.round(pct)}%</span>
                  </div>
                  <div className="h-1.5 bg-blue-200 rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-blue-500"
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{ duration: 0.3, ease: "easeOut" }}
                    />
                  </div>
                </div>
              )}
            </motion.div>
          );
        })}
        </AnimatePresence>
      </div>
    </div>
  );
}
