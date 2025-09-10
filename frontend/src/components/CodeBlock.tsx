"use client";
import React from "react";
import { useApp } from "@/lib/state/AppContext";
import { buildUrl } from "@/lib/api/config";

export function CodeBlock() {
  const { latestState, currentToolName, currentStepIndex, graph } = useApp() as any;
  const [source, setSource] = React.useState<string>("");
  const [fileName, setFileName] = React.useState<string>("");

  // When execute node is selected, fetch tool source by tool name from chosen_path
  React.useEffect(() => {
    try {
      // Priority: explicit selected tool, otherwise selected step in chosenPath, otherwise fallback to first chosen step from backend state
      let toolName: string | undefined = currentToolName;
      if (!toolName && typeof currentStepIndex === 'number' && Array.isArray(graph?.chosenPath)) {
        const nid = graph.chosenPath[currentStepIndex];
        if (nid && !/_IN$|_OUT$/i.test(nid)) toolName = nid;
      }
      if (!toolName) {
        const chosen = (latestState as any)?.chosen_path as Array<any> | undefined;
        const first = Array.isArray(chosen) && chosen.length ? (chosen[0]?.name || chosen[0]) : undefined;
        if (typeof first === 'string' && !/_IN$|_OUT$/i.test(first)) toolName = first;
      }
      if (!toolName) return;
      setFileName(`${toolName}.py`);
      fetch(buildUrl(`/api/v1/tools/source/${toolName}`))
        .then(res => res.ok ? res.json() : Promise.reject())
        .then((data) => {
          setSource(String(data?.source || ""));
        })
        .catch(() => setSource(""));
    } catch {
      setSource("");
    }
  }, [latestState, currentToolName, currentStepIndex, graph?.chosenPath]);

  return (
    <div className="h-full bg-gray-900 rounded-lg overflow-hidden border border-gray-200 flex flex-col">
      {/* File name header */}
      <div className="flex-none px-4 py-2 bg-gray-800 border-b border-gray-700">
        <div className="text-sm text-gray-300 font-medium">{fileName || "tool.py"}</div>
      </div>
      
      {/* Code content */}
      <div className="flex-1 overflow-auto p-4">
        <pre className="text-sm text-gray-300 font-mono leading-relaxed whitespace-pre-wrap">
          <code>{source || ""}</code>
        </pre>
      </div>
    </div>
  );
}
