"use client";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useApp } from "@/lib/state/AppContext";
import { Chat } from "@/components/Chat";
import { PropagationPanel } from "@/components/PropagationPanel";
import { ExecutionPanel } from "@/components/ExecutionPanel";

export default function MainArea() {
  const { showViz, showExecution, splitRatio, verticalSplitRatio, dispatch } = useApp();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rightPanelRef = useRef<HTMLDivElement | null>(null);
  const isDraggingHorizontalRef = useRef(false);
  const isDraggingVerticalRef = useRef(false);

  const [localRatio, setLocalRatio] = useState(splitRatio);
  const [localVerticalRatio, setLocalVerticalRatio] = useState(verticalSplitRatio);
  useEffect(() => setLocalRatio(splitRatio), [splitRatio]);
  useEffect(() => setLocalVerticalRatio(verticalSplitRatio), [verticalSplitRatio]);

  // Horizontal drag handlers
  const onHorizontalMouseDown = useCallback((e: React.MouseEvent) => {
    if (!showViz) return;
    isDraggingHorizontalRef.current = true;
    e.preventDefault();
  }, [showViz]);

  const onHorizontalMouseMove = useCallback((e: MouseEvent) => {
    if (!isDraggingHorizontalRef.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    let ratioLeft = x / rect.width; // chat width ratio
    const minChatPx = 420; // minimum chat width to keep buttons stable
    const minPanelRatio = 0.5; // minimum right panel width ratio
    const minChatRatio = Math.min(0.6, minChatPx / rect.width);
    ratioLeft = Math.max(minChatRatio, Math.min(1 - minPanelRatio, ratioLeft));
    const ratioRight = 1 - ratioLeft;
    setLocalRatio(ratioRight);
  }, []);

  const endHorizontalDrag = useCallback(() => {
    if (!isDraggingHorizontalRef.current) return;
    isDraggingHorizontalRef.current = false;
    dispatch({ type: "set_split_ratio", ratio: localRatio });
  }, [dispatch, localRatio]);

  // Vertical drag handlers - ALWAYS enabled when showViz is true
  const onVerticalMouseDown = useCallback((e: React.MouseEvent) => {
    if (!showViz) return; // Only require showViz, not showExecution
    isDraggingVerticalRef.current = true;
    e.preventDefault();
  }, [showViz]); // Remove showExecution dependency

  const onVerticalMouseMove = useCallback((e: MouseEvent) => {
    if (!isDraggingVerticalRef.current || !rightPanelRef.current) return;
    const rect = rightPanelRef.current.getBoundingClientRect();
    const y = e.clientY - rect.top;
    
    // Calculate minimum heights based on content requirements
    const minPropagationHeight = 200; // minimum height for propagation panel
    const minExecutionHeight = 300; // minimum height for execution panel (needs space for CodeBlock + Console)
    const totalHeight = rect.height;
    const minPropagationRatio = minPropagationHeight / totalHeight;
    const maxPropagationRatio = (totalHeight - minExecutionHeight) / totalHeight;
    
    let ratio = y / totalHeight; // propagation panel height ratio
    ratio = Math.max(minPropagationRatio, Math.min(maxPropagationRatio, ratio));
    setLocalVerticalRatio(ratio);
  }, []);

  const endVerticalDrag = useCallback(() => {
    if (!isDraggingVerticalRef.current) return;
    isDraggingVerticalRef.current = false;
    dispatch({ type: "set_vertical_split_ratio", ratio: localVerticalRatio });
  }, [dispatch, localVerticalRatio]);

  useEffect(() => {
    const onHorizontalMove = (e: MouseEvent) => onHorizontalMouseMove(e);
    const onVerticalMove = (e: MouseEvent) => onVerticalMouseMove(e);
    const onUp = () => {
      endHorizontalDrag();
      endVerticalDrag();
    };
    window.addEventListener("mousemove", onHorizontalMove);
    window.addEventListener("mousemove", onVerticalMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onHorizontalMove);
      window.removeEventListener("mousemove", onVerticalMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []); // Remove circular dependencies - these functions are stable

  const chatStyle = showViz
    ? { width: `${Math.max(0, Math.min(1, 1 - localRatio)) * 100}%` }
    : undefined;
  const panelStyle = showViz ? { width: `${Math.max(0.5, localRatio) * 100}%` } : undefined;

  return (
    <div ref={containerRef} className="h-full flex items-stretch select-none">
      <div className={`${showViz ? "flex-none" : "flex-1"}`} style={chatStyle}>
        <div className="min-w-[420px] h-full">
          <Chat logoPath={"/genesis.svg"} logoSize={200} />
        </div>
      </div>
      {showViz && (
        <>
          {/* Horizontal Drag Handle */}
          <div
            onMouseDown={onHorizontalMouseDown}
            className="relative flex-none w-[12px] cursor-col-resize bg-transparent group z-20"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize panel"
          >
            <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-px bg-gray-200 group-hover:bg-gray-300 " />
            <button
              type="button"
              onMouseDown={onHorizontalMouseDown}
              aria-label="Drag to resize"
              className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-6 w-6 rounded-full border border-gray-300 bg-white shadow-sm flex items-center justify-center hover:bg-gray-100 active:bg-gray-200 cursor-col-resize"
            >
              <span className="flex flex-col items-center justify-center gap-[2px]">
                <span className="h-0.5 w-3 bg-gray-500 rounded" />
                <span className="h-0.5 w-3 bg-gray-500 rounded" />
                <span className="h-0.5 w-3 bg-gray-500 rounded" />
              </span>
            </button>
          </div>
          
          {/* Right Panel - Always use vertical split layout */}
          <div ref={rightPanelRef} className="flex-none flex flex-col" style={panelStyle}>
            {/* Propagation Panel - Always respect vertical ratio */}
            <div 
              className="flex-none overflow-hidden relative" 
              style={{ height: `${localVerticalRatio * 100}%`, minHeight: '200px' }}
            >
              <PropagationPanel />
            </div>
            
            {/* Vertical Drag Handle - Always visible when showViz is true */}
            <div
              onMouseDown={onVerticalMouseDown}
              className="relative flex-none h-[12px] cursor-row-resize bg-transparent group z-20"
              role="separator"
              aria-orientation="horizontal"
              aria-label="Resize vertical panel"
            >
              <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-px bg-gray-200 group-hover:bg-gray-300" />
              <button
                type="button"
                onMouseDown={onVerticalMouseDown}
                aria-label="Drag to resize vertically"
                className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-6 w-6 rounded-full border border-gray-300 bg-white shadow-sm flex items-center justify-center hover:bg-gray-100 active:bg-gray-200 cursor-row-resize z-20"
              >
                <span className="flex flex-col items-center justify-center gap-[2px]">
                  <span className="h-0.5 w-3 bg-gray-500 rounded" />
                  <span className="h-0.5 w-3 bg-gray-500 rounded" />
                  <span className="h-0.5 w-3 bg-gray-500 rounded" />
                </span>
              </button>
            </div>
            
            {/* Execution Panel - Always takes remaining space */}
            <div 
              className="flex-1 overflow-hidden relative" 
              style={{ height: `${(1 - localVerticalRatio) * 100}%`, minHeight: '200px' }}
            >
              <ExecutionPanel />
            </div>
          </div>
        </>
      )}
    </div>
  );
}