"use client";
import React from "react";
import { useApp } from "@/lib/state/AppContext";
import { CodeBlock } from "@/components/CodeBlock";
import { Console } from "@/components/Console";
import { Preview } from "@/components/Preview";

export function ExecutionPanel() {
  const { showExecution, dispatch, latestState } = useApp() as any;
  const hasPrimary = Boolean(latestState?.execution_output_path);
  const shouldShow = showExecution || hasPrimary;
  
  return (
    <div className="h-full w-full bg-white flex flex-col overflow-hidden">
      <div className="flex items-center justify-between p-4 flex-none">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-orange-500 rounded-full"></div>
          <h3 className="text-base font-semibold text-gray-900">Execution</h3>
        </div>
        <button
          onClick={() => dispatch({ type: "toggle_show_execution" })}
          className={`px-3 py-1 text-xs rounded-md border transition-colors ${
            showExecution 
              ? "bg-gray-900 text-white border-gray-900" 
              : "bg-gray-50 text-gray-700 border-gray-200 hover:bg-gray-100"
          }`}
        >
          {showExecution ? "Hide" : "Show"}
        </button>
      </div>
      
      {shouldShow && (
        <div className="flex-1 min-h-0 p-4 overflow-hidden">
          <div className="grid grid-cols-2 gap-4 h-full">
            {/* Left Column: CodeBlock on top, Console on bottom */}
            <div className="flex flex-col gap-4 min-h-0">
              {/* CodeBlock (Top) - takes up to 50% of available height */}
              <div className="flex-1 bg-gray-50 rounded-lg overflow-hidden min-h-[60px]">
                <CodeBlock />
              </div>
              
              {/* Console (Bottom) - takes up to 50% of available height */}
              <div className="flex-1 bg-gray-50 rounded-lg overflow-hidden min-h-[60px]">
                <Console />
              </div>
            </div>
            
            {/* Right Column: Preview (Full height) */}
            <div className="bg-gray-50 rounded-lg overflow-hidden min-h-0">
              <Preview />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}