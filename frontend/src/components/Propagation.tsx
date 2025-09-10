"use client";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useApp } from "@/lib/state/AppContext";
import { calculateNodePositions } from "@/lib/graph/layout";

type Step = { from: string; to: string };

const edgeId = (a: string, b: string) => `${a}->${b}`;

function svgCurve(from: { x: number; y: number }, to: { x: number; y: number }) {
  const dx = (to.x - from.x) / 2;
  const c1 = { x: from.x + dx, y: from.y };
  const c2 = { x: to.x - dx, y: to.y };
  return `M ${from.x} ${from.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${to.x} ${to.y}`;
}

// (removed experimental obstacle-aware routing helpers)


export default function Propagation() {
  const { graph, dispatch, currentConversationId, stage, currentToolName, currentStepIndex } = useApp();
  // SNAPSHOT: store candidates seen at populate start
  const candidateSnapshotRef = useRef<string[][]>([]);
  
  // Helper function to get endpoint nodes from the graph
  const getEndpointNodesFromGraph = (): string[] => {
    const endpoints: string[] = [];
    const allNodes = new Set<string>();
    
    // Collect all nodes from paths
    graph.allPaths.forEach(path => {
      if (path) path.forEach(node => allNodes.add(node));
    });
    
    // Find endpoint nodes (nodes that match known endpoint patterns)
    const endpointPatterns = ['_IN', '_OUT'];
    for (const node of allNodes) {
      if (endpointPatterns.some(pattern => node.includes(pattern))) {
        endpoints.push(node);
      }
    }
    
    // Fallback to legacy endpoints if no dynamic endpoints found
    if (endpoints.length === 0) {
      return ['IMAGE_IN', 'IMAGE_OUT'];
    }
    
    return endpoints;
  };
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(graph.population?.speed || 1);
  const [edgeIndex, setEdgeIndex] = useState(0);
  const [viewBox, setViewBox] = useState("0 0 1120 360");
  const [containerSize, setContainerSize] = useState<{ w: number; h: number }>({ w: 1120, h: 360 });
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Animation state for find_path vs chosen_path vs reduce modes
  const [animationMode, setAnimationMode] = useState<'chosen_path' | 'find_path' | 'reduce'>('chosen_path');
  const [currentPathIndex, setCurrentPathIndex] = useState(0);
  const [revealedNodes, setRevealedNodes] = useState<Set<string>>(new Set());
  const [revealedEdges, setRevealedEdges] = useState<Set<string>>(new Set()); // Track which edges should be visible
  const [highlightedEdges, setHighlightedEdges] = useState<Set<string>>(new Set()); // Track which visible edges are highlighted
  
  // Determine output endpoint id for finalize stage
  const outputEndpointId = useMemo(() => {
    const eps = getEndpointNodesFromGraph();
    const out = eps.find(e => e.includes('_OUT'));
    return out || 'IMAGE_OUT';
  }, [graph.allPaths, graph.inputType, graph.outputType]);

  // Currently executing node from execution events (or output when finalize)
  const executingNodeId = useMemo(() => {
    if (stage === 'finalize') return outputEndpointId;
    if (currentToolName && typeof currentToolName === 'string') return currentToolName;
    if (typeof currentStepIndex === 'number' && graph.chosenPath && currentStepIndex >= 0 && currentStepIndex < graph.chosenPath.length) {
      return graph.chosenPath[currentStepIndex];
    }
    return undefined;
  }, [stage, outputEndpointId, currentToolName, currentStepIndex, graph.chosenPath]);

  // Reduce animation state
  const [populateCompleted, setPopulateCompleted] = useState(false);
  const [reduceStarted, setReduceStarted] = useState(false);
  const [pathsToEliminate, setPathsToEliminate] = useState<string[][]>([]);
  const [eliminatedPaths, setEliminatedPaths] = useState<Set<string>>(new Set());
  const [currentHighlightedPath, setCurrentHighlightedPath] = useState<string[] | null>(null);

  // Track which paths set we've initialized populate animation for
  const pathsKey = useMemo(() => JSON.stringify(graph.allPaths || []), [graph.allPaths]);
  const initializedForPathsRef = useRef<string | null>(null);

  // Determine which paths to render
  const hasChosenPath = graph.chosenPath && graph.chosenPath.length > 0;
  const pathsToRender = useMemo(() => {
    if (graph.currentPaths && graph.currentPaths.length > 0) return graph.currentPaths;
    if (hasChosenPath && graph.chosenPath) return [graph.chosenPath];
    return graph.allPaths;
  }, [graph.currentPaths, hasChosenPath, graph.chosenPath, graph.allPaths]);
  const pathsToShow = pathsToRender;
  
  // Determine animation mode and sequence: find_path -> reduce -> chosen_path
  useEffect(() => {
    if (stage === 'route' && hasChosenPath && !reduceStarted && populateCompleted) {
      console.log('[Reduce] Triggered: entering reduce mode', {
        stage,
        populateCompleted,
        hasChosenPath,
        pathsCount: graph.allPaths.length,
        chosenPath: graph.chosenPath,
      });
      // Start reduce animation when entering route state and populate is done
      setAnimationMode('reduce');
      dispatch({ type: "set_animation_mode", mode: 'reduce' });
      setReduceStarted(true);
      dispatch({ type: "set_reduce_started", started: true });
      
      // Prepare paths to eliminate (all paths except chosen path)
      const pathsToRemove = graph.allPaths.filter(path => {
        if (!path || !graph.chosenPath) return true;
        return JSON.stringify(path) !== JSON.stringify(graph.chosenPath);
      });
      setPathsToEliminate(pathsToRemove);
      console.log('[Reduce] Paths scheduled for elimination (excluding chosen):', pathsToRemove);
      setCurrentPathIndex(0);
      dispatch({ type: "set_reduce_index", index: 0 });
      setEliminatedPaths(new Set());
      
    } else if (hasChosenPath && !populateCompleted) {
      // If chosen path arrives before populate completes, wait for populate
      // Do nothing, let populate finish first
      
    } else if (!hasChosenPath && graph.allPaths.length > 0) {
      // Normal find_path mode (populate). Only initialize once per unique paths set.
      if (initializedForPathsRef.current !== pathsKey) {
        initializedForPathsRef.current = pathsKey;
        setAnimationMode('find_path');
        dispatch({ type: "set_animation_mode", mode: 'find_path' });
        setPopulateCompleted(false);
        dispatch({ type: "set_populate_completed", completed: false });
        setReduceStarted(false);
        dispatch({ type: "set_reduce_started", started: false });
        // Start with only endpoint nodes visible and NO edges visible
        // Use dynamic endpoints based on workflow type
        const endpointNodes = getEndpointNodesFromGraph();
        setRevealedNodes(new Set(endpointNodes));
        setRevealedEdges(new Set()); // No edges visible initially
        setHighlightedEdges(new Set());
        setCurrentPathIndex(0);
        dispatch({ type: "set_populate_index", index: 0 });
        setPathsToEliminate([]);
        setEliminatedPaths(new Set());
        // Initialize UI-ephemeral currentPaths and snapshot candidates
        // Start with an empty list (no [in_node, out_node] stub)
        dispatch({ type: 'ui/reset_for_find_path' });
        candidateSnapshotRef.current = (graph.allPaths || []).map(p => [...p]);
      }
    }
  }, [stage, hasChosenPath, graph.chosenPath, graph.allPaths.length, populateCompleted, reduceStarted, pathsKey, dispatch]);

  // Build ALL possible edges, but only render those that have been revealed
  const bgEdges = useMemo(() => {
    const edges = new Map<string, { id: string; from: string; to: string }>();
    const pathsToProcess = pathsToRender;
    
    for (const p of pathsToProcess) {
      if (p && p.length > 1) {
        for (let i = 0; i < p.length - 1; i++) {
          const a = p[i], b = p[i + 1];
          edges.set(edgeId(a, b), { id: edgeId(a, b), from: a, to: b });
        }
      }
    }
    return Array.from(edges.values());
  }, [pathsToRender]);

  // Fast find_path animation timing - now path-by-path instead of step-by-step
  const FIND_PATH_DURATION = 300; // milliseconds per complete path
  const PATH_PAUSE = 200; // pause between paths
  
  // New path-by-path animation logic
  useEffect(() => {
    if (animationMode !== 'find_path' || !playing || graph.allPaths.length === 0) return;
    
    if (currentPathIndex >= graph.allPaths.length) {
      // Animation completed - mark populate as complete
      if (!populateCompleted) {
        setPopulateCompleted(true);
        dispatch({ type: "set_populate_completed", completed: true });
      }
      return;
    }
    
    const currentPath = graph.allPaths[currentPathIndex];
    if (!currentPath || currentPath.length < 2) {
      // Skip invalid paths and move to next
      setTimeout(() => {
        const next = currentPathIndex + 1;
        setCurrentPathIndex(next);
        dispatch({ type: "set_populate_index", index: next });
      }, 50);
      return;
    }
    
    setTimeout(() => {
      // Step 1: Reveal all nodes in this path first
      const pathNodes = new Set(currentPath);
      setRevealedNodes(prev => new Set([...prev, ...pathNodes]));
      
      // Step 2: Reveal and highlight all edges in this path
      const pathEdges = new Set<string>();
      for (let i = 0; i < currentPath.length - 1; i++) {
        const from = currentPath[i];
        const to = currentPath[i + 1];
        const edgeIdStr = `${from}->${to}`;
        pathEdges.add(edgeIdStr);
      }
      
      // Reveal the edges (make them visible)
      setRevealedEdges(prev => new Set([...prev, ...pathEdges]));
      // Highlight the edges (current path)
      setHighlightedEdges(pathEdges);
      console.log('[Populate] Revealing and highlighting path', {
        currentPathIndex,
        path: currentPath,
        pathEdges: Array.from(pathEdges),
      });
      // Append path into UI-ephemeral currentPaths for rendering
      dispatch({ type: 'ui/append_current_path', path: currentPath });
      
      // Move to next path after duration + pause
      setTimeout(() => {
        if (currentPathIndex < graph.allPaths.length - 1) {
          const next = currentPathIndex + 1;
          setCurrentPathIndex(next);
          dispatch({ type: "set_populate_index", index: next });
          setHighlightedEdges(new Set()); // Clear highlights for new path (but keep edges visible)
        } else {
          // Last path completed
          const next = currentPathIndex + 1;
          setCurrentPathIndex(next);
          dispatch({ type: "set_populate_index", index: next }); // This will trigger completion in next cycle
        }
      }, FIND_PATH_DURATION + PATH_PAUSE);
      
    }, 0); // Start immediately
  }, [animationMode, playing, currentPathIndex, graph.allPaths, populateCompleted, dispatch]);

  // Reduce animation logic - eliminate paths one by one
  const REDUCE_HIGHLIGHT_DURATION = 800; // milliseconds to highlight before removal
  const REDUCE_PAUSE = 400; // pause between eliminations
  
  useEffect(() => {
    if (animationMode !== 'reduce') return;
    // Edge case: nothing to eliminate (e.g., all_paths already reduced to chosen_path)
    if (pathsToEliminate.length === 0) {
      console.log('[Reduce] No paths to eliminate. Finalizing to chosen_path');
      setAnimationMode('chosen_path');
      dispatch({ type: "set_animation_mode", mode: 'chosen_path' });
      if (graph.chosenPath) {
        const chosenNodes = new Set<string>();
        const chosenEdges = new Set<string>();
        graph.chosenPath.forEach(node => chosenNodes.add(node));
        for (let i = 0; i < graph.chosenPath.length - 1; i++) {
          chosenEdges.add(`${graph.chosenPath[i]}->${graph.chosenPath[i + 1]}`);
        }
        setRevealedNodes(chosenNodes);
        setRevealedEdges(chosenEdges);
        setHighlightedEdges(new Set());
        dispatch({ type: "set_reduce_animation_completed", completed: true });
      }
      return;
    }
    
    if (currentPathIndex >= pathsToEliminate.length) {
      // All paths eliminated - switch to final chosen_path mode
      setAnimationMode('chosen_path');
      dispatch({ type: "set_animation_mode", mode: 'chosen_path' });
      // Show only chosen path nodes and edges
      if (graph.chosenPath) {
        const chosenNodes = new Set<string>();
        const chosenEdges = new Set<string>();
        
        graph.chosenPath.forEach(node => chosenNodes.add(node));
        for (let i = 0; i < graph.chosenPath.length - 1; i++) {
          chosenEdges.add(`${graph.chosenPath[i]}->${graph.chosenPath[i + 1]}`);
        }
        
        setRevealedNodes(chosenNodes);
        setRevealedEdges(chosenEdges);
        setHighlightedEdges(new Set());
        
        // Notify that reduce animation is completed
        dispatch({ type: "set_reduce_animation_completed", completed: true });
      }
      return;
    }
    
    const pathToEliminate = pathsToEliminate[currentPathIndex];
    if (!pathToEliminate || pathToEliminate.length < 2) {
      // Skip invalid paths
      setTimeout(() => {
        setCurrentPathIndex(prev => prev + 1);
      }, 50);
      return;
    }
    
    // Generate unique ID for this path
    const pathId = pathToEliminate.join('->')
    if (eliminatedPaths.has(pathId)) {
      // Already eliminated, skip
      setTimeout(() => {
        setCurrentPathIndex(prev => prev + 1);
      }, 50);
      return;
    }
    
    setTimeout(() => {
      // Step 1: Highlight the path to be eliminated
      const pathEdges = new Set<string>();
      for (let i = 0; i < pathToEliminate.length - 1; i++) {
        pathEdges.add(`${pathToEliminate[i]}->${pathToEliminate[i + 1]}`);
      }
      setHighlightedEdges(pathEdges);
      
      // Also highlight the path locally
      setCurrentHighlightedPath(pathToEliminate);
      
      // Step 2: After highlight duration, remove the path and check for disconnected nodes
      setTimeout(() => {
        // Remove path edges and recompute connected nodes from the UPDATED edge set
        setRevealedEdges(prev => {
          const newEdges = new Set(prev);

          // Build a set of edges that must be kept because they are used by other remaining paths or the chosen path
          const edgeInOtherPaths = new Set<string>();
          try {
            const eliminatedId = JSON.stringify(pathToEliminate);
            const remainingPaths: string[][] = (graph.currentPaths || []).filter(p => JSON.stringify(p) !== eliminatedId);
            if (graph.chosenPath && graph.chosenPath.length) remainingPaths.push(graph.chosenPath);
            for (const p of remainingPaths) {
              for (let i = 0; i < p.length - 1; i++) {
                edgeInOtherPaths.add(`${p[i]}->${p[i + 1]}`);
              }
            }
          } catch {}

          // Only remove edges that are NOT used by any other remaining path
          pathEdges.forEach(edge => { if (!edgeInOtherPaths.has(edge)) newEdges.delete(edge); });

          const connectedNodes = new Set<string>();
          // Build connectivity from the newEdges set
          newEdges.forEach(edgeId => {
            const [from, to] = edgeId.split('->');
            if (from) connectedNodes.add(from);
            if (to) connectedNodes.add(to);
          });

          // Always keep nodes on the chosen path during reduce
          if (graph.chosenPath) {
            graph.chosenPath.forEach(node => connectedNodes.add(node));
          }

          // Always include endpoints
          const endpointNodes = getEndpointNodesFromGraph();
          endpointNodes.forEach(node => connectedNodes.add(node));

          // Apply node visibility from the recomputed connectivity
          setRevealedNodes(connectedNodes);
          console.log('[Reduce] Removed edges and updated revealed nodes', {
            removedEdges: Array.from(pathEdges).filter(e => !edgeInOtherPaths.has(e)),
            remainingEdges: Array.from(newEdges),
            connectedNodes: Array.from(connectedNodes),
          });
          return newEdges;
        });
        
        // Remove from currentPaths too
        dispatch({ type: 'ui/remove_current_path', pathId: JSON.stringify(pathToEliminate) });
        // Mark path as eliminated
        setEliminatedPaths(prev => new Set([...prev, pathId]));
        
        // Clear highlights and move to next path
        setHighlightedEdges(new Set());
        setCurrentHighlightedPath(null);
        setTimeout(() => {
          const next = currentPathIndex + 1;
          setCurrentPathIndex(next);
          dispatch({ type: "set_reduce_index", index: next });
          console.log('[Reduce] Advancing to next elimination index', { next });
        }, REDUCE_PAUSE);
        
      }, REDUCE_HIGHLIGHT_DURATION);
      
    }, 0);
  }, [animationMode, currentPathIndex, pathsToEliminate, eliminatedPaths, revealedEdges, graph.chosenPath, dispatch]);

  const animatedSteps: Step[] = useMemo(() => {
    if (animationMode === 'chosen_path') {
      const p = pathsToShow[0] || [];
      const steps: Step[] = [];
      for (let i = 0; i < p.length - 1; i++) steps.push({ from: p[i], to: p[i + 1] });
      return steps;
    }
    return []; // No traditional animation steps for find_path mode
  }, [pathsToShow, animationMode]);
  
  // Create a set of nodes that are in the active path for highlighting
  const activeNodes = useMemo(() => {
    if (animationMode === 'chosen_path') {
      const nodes = new Set<string>();
      pathsToShow.forEach(path => {
        if (path) {
          path.forEach(node => nodes.add(node));
        }
      });
      return nodes;
    } else {
      // For find_path and reduce modes, active nodes are the ones revealed so far
      return revealedNodes;
    }
  }, [pathsToShow, animationMode, revealedNodes]);

  // Nodes to render: for chosen_path show active nodes, for find_path and reduce show all possible nodes but control visibility
  const nodesToRender = useMemo(() => {
    if (animationMode === 'chosen_path') {
      return Array.from(activeNodes);
    } else {
      // For find_path and reduce modes, render all nodes that could be in any path but control visibility separately
      const allNodes = new Set<string>();
      graph.allPaths.forEach(path => {
        if (path) {
          path.forEach(node => allNodes.add(node));
        }
      });
      return Array.from(allNodes);
    }
  }, [activeNodes, animationMode, graph.allPaths]);

  const BASE_EDGE_SECONDS = 1.6;
  const edgeDuration = BASE_EDGE_SECONDS / (speed || 1);

  // Only animate edge cycling in chosen_path mode if user wants it (currently disabled for static display)
  useEffect(() => {
    // Disable all edge cycling animation in chosen_path mode for static display
    if (animationMode === 'chosen_path') return;
    if (!playing) return;
    if (!animatedSteps.length) return;
    const timeout = setTimeout(() => {
      setEdgeIndex((i) => (i < animatedSteps.length - 1 ? i + 1 : 0));
    }, edgeDuration * 1000);
    return () => clearTimeout(timeout);
  }, [animationMode, playing, animatedSteps.length, edgeDuration, edgeIndex]);

  // No cycling edge in chosen_path mode - just static highlighting
  const currentEdge = animationMode === 'chosen_path' ? null : animatedSteps[edgeIndex];
  const activeId = currentEdge ? edgeId(currentEdge.from, currentEdge.to) : "";
  
  // Deterministic seed from thread/conversation id
  const layoutSeed = useMemo(() => {
    if (!currentConversationId) return undefined;
    let h = 0;
    for (let i = 0; i < currentConversationId.length; i++) {
      h = (h * 131 + currentConversationId.charCodeAt(i)) >>> 0;
    }
    return h & 0xFFFFFFFF;
  }, [currentConversationId]);

  // Track first load and previous values for optimization
  const prevPathsRef = useRef<string>("");
  const prevSizeRef = useRef<{ w: number; h: number }>({ w: 0, h: 0 });
  const isFirstLoadRef = useRef(true);

  // Recalculate positions only when needed: first load, paths change, or significant resize
  useEffect(() => {
    if (!graph.allPaths.length) return;
    
    // Create a stable string representation of paths for comparison
    const pathsKey = JSON.stringify(graph.allPaths);
    const sizeChanged = Math.abs(containerSize.w - prevSizeRef.current.w) > 50 || 
                      Math.abs(containerSize.h - prevSizeRef.current.h) > 50;
    
    // Only recalculate if: first load, paths changed, or significant resize
    if (!isFirstLoadRef.current && 
        pathsKey === prevPathsRef.current && 
        !sizeChanged) {
      return;
    }
    
    console.log("Recalculating positions:", {
      isFirstLoad: isFirstLoadRef.current,
      pathsChanged: pathsKey !== prevPathsRef.current,
      sizeChanged,
      newSize: containerSize,
      prevSize: prevSizeRef.current,
      toolMetadataCount: graph.toolMetadata.length,
      architecture: "toolMetadata-driven positioning"
    });
    
    const cw = Math.max(1, Math.floor(containerSize.w));
    const ch = Math.max(1, Math.floor(containerSize.h));
    const next = calculateNodePositions(graph.toolMetadata, graph.allPaths, cw, ch, {}, 64, 20, layoutSeed);
    const curr = graph.positions;
    const aKeys = Object.keys(next);
    const bKeys = Object.keys(curr);
    let changed = aKeys.length !== bKeys.length;
    if (!changed) {
      for (const k of aKeys) {
        const a = next[k]; const b = curr[k];
        if (!b || Math.abs(a.x - b.x) > 0.001 || Math.abs(a.y - b.y) > 0.001) { changed = true; break; }
      }
    }
    if (changed) {
      dispatch({ type: "set_graph_style", colors: graph.colors, positions: next });
    }
    
    // Update tracking variables
    prevPathsRef.current = pathsKey;
    prevSizeRef.current = { w: containerSize.w, h: containerSize.h };
    isFirstLoadRef.current = false;
  }, [graph.toolMetadata, graph.allPaths, containerSize.w, containerSize.h, layoutSeed]);

  // Render-time pinning of endpoints back to previous position
  const renderPositions = useMemo(() => {
    const rp: Record<string, { x: number; y: number }> = {};
    const LEFT_MARGIN = 60; // pixel margin
    const RIGHT_MARGIN = 60; // pixel margin
    
    // Calculate base positions for all nodes (only actual nodes, not legacy IMG)
    const relevantPositions = Object.keys(graph.positions).filter(k => k !== "IMG"); // Filter out legacy IMG node
    if (relevantPositions.length === 0) return {};
    
    const minX = Math.min(...relevantPositions.map(k => graph.positions[k]?.x || 0).filter(x => isFinite(x)));
    const maxX = Math.max(...relevantPositions.map(k => graph.positions[k]?.x || 0).filter(x => isFinite(x)));
    
    const leftX = minX - LEFT_MARGIN;
    const rightX = maxX + RIGHT_MARGIN;
    
    for (const k of nodesToRender) {
      const p = graph.positions[k];
      if (!p) {
        console.warn(`Missing position for node: ${k}`);
        // Provide fallback position to prevent undefined access
        rp[k] = { x: 0, y: 0 };
        continue;
      }
      let x = p.x;
      // Pin endpoint nodes to margins (dynamic endpoint detection)
      if (k.includes("_IN")) x = leftX;
      if (k.includes("_OUT")) x = rightX;
      rp[k] = { x, y: p.y };
    }
    return rp;
  }, [graph.positions, nodesToRender]);

  // Check if positions exist before creating curve
  const fromPos = currentEdge ? renderPositions[currentEdge.from] : null;
  const toPos = currentEdge ? renderPositions[currentEdge.to] : null;
  const activeD = currentEdge && fromPos && toPos ? svgCurve(fromPos, toPos) : "";
  
  // Debug logging for edge highlighting (simple lines, no arrows)
  console.log("Edge Highlighting Debug:", {
    currentEdge,
    activeId,
    fromPos,
    toPos,
    activeD,
    playing,
    edgeIndex,
    animatedStepsLength: animatedSteps.length,
    highlightColor: "#6366f1",
    normalColor: "#e2e8f0",
    activeStrokeWidth: 4,
    normalStrokeWidth: 2,
    arrows: "removed"
  });

  // Track container size with resize observer (no viewBox calc here)
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const handle = () => {
      const rect = el.getBoundingClientRect();
      const w = Math.floor(rect.width), h = Math.floor(rect.height);
      setContainerSize(prev => (prev.w === w && prev.h === h ? prev : { w, h }));
    };
    handle();
    const ro = new ResizeObserver(handle);
    ro.observe(el);
    window.addEventListener("resize", handle);
    return () => { ro.disconnect(); window.removeEventListener("resize", handle); };
  }, []);

  // Fit viewBox based on render positions and current container size
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const rect = el.getBoundingClientRect();
    const pts = nodesToRender.map(n => renderPositions[n]).filter(Boolean) as Array<{x:number;y:number}>;
    if (!pts.length) return;
    const xs = pts.map((p) => p.x).filter(x => isFinite(x));
    const ys = pts.map((p) => p.y).filter(y => isFinite(y));
    if (xs.length === 0 || ys.length === 0) { 
      const newViewBox = "0 0 1120 360";
      setViewBox(prev => prev === newViewBox ? prev : newViewBox); 
      return; 
    }
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    if (!isFinite(minX) || !isFinite(maxX) || !isFinite(minY) || !isFinite(maxY) || Math.abs(maxX - minX) > 10000 || Math.abs(maxY - minY) > 10000) {
      const newViewBox = "0 0 1120 360";
      setViewBox(prev => prev === newViewBox ? prev : newViewBox);
      return;
    }
    // Use tighter padding so the graph scales closer to full canvas
    const contentLeft = minX - 40, contentRight = maxX + 40;
    const contentTop = minY - 30, contentBottom = maxY + 30;
    const contentWidth = contentRight - contentLeft;
    const contentHeight = contentBottom - contentTop;
    const MARGIN_H = 20, MARGIN_V = 12;
    const scaleX = (rect.width - 2 * MARGIN_H) / contentWidth;
    const scaleY = (rect.height - 2 * MARGIN_V) / contentHeight;
    // Remove 1.5 cap so we don't force extra zooming out
    const scale = Math.min(scaleX, scaleY);
    let viewX, viewY, viewW, viewH;
    if (scale === scaleX) {
      viewW = contentWidth; viewH = rect.height / scale; viewX = contentLeft; viewY = contentTop + (contentHeight - viewH) / 2;
    } else {
      viewH = contentHeight; viewW = rect.width / scale; viewX = contentLeft + (contentWidth - viewW) / 2; viewY = contentTop;
    }
    const marginInSvgUnits = MARGIN_H / scale; viewX -= marginInSvgUnits; viewW += 2 * marginInSvgUnits;
    const marginVInSvgUnits = MARGIN_V / scale; viewY -= marginVInSvgUnits; viewH += 2 * marginVInSvgUnits;
    if (viewW <= 0 || viewH <= 0 || !isFinite(viewX) || !isFinite(viewY) || !isFinite(viewW) || !isFinite(viewH)) {
      const newViewBox = "0 0 1120 360";
      setViewBox(prev => prev === newViewBox ? prev : newViewBox);
    } else {
      const newViewBox = `${viewX} ${viewY} ${viewW} ${viewH}`;
      setViewBox(prev => prev === newViewBox ? prev : newViewBox);
    }
  }, [renderPositions, nodesToRender, containerSize.w, containerSize.h]);

  // (duplicate renderPositions removed)

  // Calculate SVG scale to maintain fixed node sizes
  const svgScale = useMemo(() => {
    if (!containerSize.w || !containerSize.h) return 1;
    const parts = viewBox.split(" ").map(parseFloat);
    if (parts.length !== 4) return 1;
    const [vx, vy, vw, vh] = parts;
    const scaleX = containerSize.w / vw;
    const scaleY = containerSize.h / vh;
    const scale = Math.min(scaleX, scaleY);
    return isFinite(scale) && scale > 0 ? scale : 1;
  }, [viewBox, containerSize.w, containerSize.h]);

  // Fixed node dimensions in pixels
  const FIXED_NODE_WIDTH = 88;
  const FIXED_NODE_HEIGHT = 34;
  const FIXED_FONT_SIZE = 14;
  const FIXED_STROKE_WIDTH = 1;

  // Scale-adjusted dimensions to maintain fixed pixel sizes
  const nodeWidth = FIXED_NODE_WIDTH / svgScale;
  const nodeHeight = FIXED_NODE_HEIGHT / svgScale;
  const fontSize = FIXED_FONT_SIZE / svgScale;
  const strokeWidth = FIXED_STROKE_WIDTH / svgScale;
  // (removed obstacle-aware rects and routing; back to simple curves)

  // Debug logging for overall graph state
  console.log("=== Propagation Component Debug ===");
  console.log("Graph State:", {
    allPaths: graph.allPaths,
    chosenPath: graph.chosenPath,
    hasChosenPath: hasChosenPath,
    pathsToShow: pathsToShow,
    positions: graph.positions,
    colors: graph.colors,
    nodesToRender: nodesToRender,
    activeNodes: Array.from(activeNodes),
    bgEdges: bgEdges,
    currentEdge: currentEdge,
    viewBox: viewBox,
    containerSize: containerSize,
    svgScale: svgScale,
    nodeWidth: nodeWidth,
    nodeHeight: nodeHeight
  });

  // Check if we have valid graph data
  if (!graph.allPaths.length || !Object.keys(graph.positions).length) {
    console.log("No valid graph data - showing waiting message");
    return (
      <div className="w-full h-full grid place-items-center text-sm text-slate-500">
        Waiting for paths...
      </div>
    );
  }

  return (
    <div ref={containerRef} className="w-full h-full bg-white">
      <div className="relative h-full rounded-2xl border border-slate-200 bg-white overflow-hidden">
        <div className="absolute z-10 top-3 left-3 flex items-center gap-3 bg-white/70 backdrop-blur rounded-xl px-3 py-2 shadow border border-slate-200">
          {animationMode === 'find_path' && (
            <>
              <button onClick={() => setPlaying((p) => !p)} className="px-2 py-1 text-sm rounded-md border border-slate-200 hover:bg-slate-50">
                {playing ? "Pause" : "Play"}
              </button>
              <button 
                onClick={() => {
                  setCurrentPathIndex(0);
                  const endpointNodes = getEndpointNodesFromGraph();
                  setRevealedNodes(new Set(endpointNodes));
                  setRevealedEdges(new Set());
                  setHighlightedEdges(new Set());
                }} 
                className="px-2 py-1 text-sm rounded-md border border-slate-200 hover:bg-slate-50"
              >
                Restart
              </button>
            </>
          )}
          <span className="text-xs text-slate-500">
            {animationMode === 'find_path' 
              ? `Revealing paths... (${currentPathIndex + 1}/${graph.allPaths.length})`
              : animationMode === 'reduce'
              ? `Eliminating paths... (${currentPathIndex + 1}/${pathsToEliminate.length})`
              : `Selected path - Static`
            }
          </span>
        </div>

        <svg viewBox={viewBox} preserveAspectRatio="xMidYMid meet" className="w-full h-full">

          {bgEdges.map(({ id, from, to }) => {
            const fromPos = renderPositions[from];
            const toPos = renderPositions[to];
            if (!fromPos || !toPos) return null;
            
            // Only render edges that have been revealed (except in chosen_path mode where all edges should show)
            if (animationMode !== 'chosen_path' && !revealedEdges.has(id)) {
              return null;
            }
            
            // Determine if edge should be highlighted based on mode
            let isActiveEdge = false;
            if (animationMode === 'chosen_path') {
              // In chosen_path mode, highlight ALL edges in the chosen path (static display)
              isActiveEdge = true; // All edges in bgEdges are part of the chosen path
            } else if (animationMode === 'find_path' || animationMode === 'reduce') {
              isActiveEdge = highlightedEdges.has(id);
            }
            
            return (
              <motion.path 
                key={id} 
                id={id} 
                d={svgCurve(fromPos, toPos)} 
                stroke={isActiveEdge ? "#6366f1" : "#e2e8f0"} 
                strokeWidth={isActiveEdge ? 3 : 2} 
                fill="none" 
                initial={false}
                animate={{
                  stroke: isActiveEdge ? "#6366f1" : "#e2e8f0",
                  strokeWidth: isActiveEdge ? 3 : 2
                }}
                transition={{ duration: 0.1, ease: "easeInOut" }}
              />
            );
          })}


          {nodesToRender.map((nid) => {
            const isInActivePath = activeNodes.has(nid);
            const isEndpointNode = nid.includes("_IN") || nid.includes("_OUT");
            // Treat executing node as current; otherwise fall back to animated currentEdge during path animation
            const isCurrentNode = executingNodeId ? (executingNodeId === nid) : (nid === currentEdge?.to || nid === currentEdge?.from);
            
            // Handle visibility and opacity based on animation mode
            let opacity = 1;
            let isVisible = true;
            
            if (animationMode === 'chosen_path') {
              // Chosen path mode: endpoint nodes always visible, others fade when not in path
              opacity = hasChosenPath && !isInActivePath && !isEndpointNode ? 0.3 : 1;
              isVisible = true;
            } else if (animationMode === 'find_path' || animationMode === 'reduce') {
              // Find path and reduce modes: only show revealed nodes
              isVisible = revealedNodes.has(nid);
              opacity = isVisible ? 1 : 0;
            }
            
            const nodeColor = isEndpointNode ? "#CBDCEB" : (graph.colors[nid] || "#f8fafc");
            const nodePosition = renderPositions[nid];
            
            // Debug logging for path-by-path animation (reduced)
            if (isEndpointNode) {
              console.log(`Node [${nid}]:`, {
                pos: nodePosition,
                mode: animationMode,
                visible: isVisible,
                revealed: revealedNodes.has(nid)
              });
            }
            
            if (!isVisible && (animationMode === 'find_path' || animationMode === 'reduce')) {
              return null; // Don't render unrevealed nodes in find_path and reduce modes
            }
            
            const handleClick = () => {
              // Always select clicked node; if chosenPath index not found, use 0
              let stepIndex = 0;
              if (Array.isArray(graph.chosenPath) && graph.chosenPath.length) {
                const idx = graph.chosenPath.findIndex((n) => n === nid);
                if (idx >= 0) stepIndex = idx;
              }
              dispatch({ type: "select_execution_step", tool_name: nid, step_index: stepIndex });
            };

            return (
              <g key={nid} transform={`translate(${renderPositions[nid].x}, ${renderPositions[nid].y})`}>
                <motion.g
                  initial={{ 
                    opacity: animationMode === 'find_path' ? 0 : opacity,
                    scale: 1
                  }}
                  animate={{ 
                    opacity,
                    scale: (() => {
                      if (!isCurrentNode) return 1;
                      const bump = 5 / svgScale; // convert +5px to SVG units
                      const scaleFactor = 1 + bump / Math.max(1e-6, nodeWidth);
                      return scaleFactor;
                    })()
                  }}
                  transition={{ 
                    type: animationMode === 'find_path' ? "spring" : "spring", 
                    stiffness: 400, 
                    damping: 25,
                    duration: animationMode === 'find_path' ? 0.15 : 0.12
                  }}
                  onClick={handleClick}
                  style={{ cursor: 'pointer' }}
                >
                  <rect 
                    x={-nodeWidth/2} 
                    y={-nodeHeight/2} 
                    rx={10 / svgScale} 
                    ry={10 / svgScale} 
                    width={nodeWidth} 
                    height={nodeHeight} 
                    fill={nodeColor} 
                    stroke="none"
                  />
                  <text 
                    textAnchor="middle" 
                    y={3 / svgScale} 
                    className={`font-medium select-none ${isInActivePath || isEndpointNode ? 'fill-slate-900' : 'fill-slate-600'}`}
                    fontSize={fontSize}
                  >
                    <tspan>{nid}</tspan>
                  </text>
                </motion.g>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}