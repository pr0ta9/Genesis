"use client";
import React, { useState, useEffect, useRef } from "react";
import { useApp } from "@/lib/state/AppContext";
import { buildUrl } from "@/lib/api/config";

interface TerminalLine {
  id: number;
  content: string;
  type: 'output' | 'error' | 'input';
  timestamp: Date;
}

function resolveOutputUrl(relOrAbsPath: string): string {
  if (/^https?:\/\//i.test(relOrAbsPath)) return relOrAbsPath;
  const norm = String(relOrAbsPath).replace(/\\/g, "/");
  const rel = norm.includes('/outputs/') ? norm.split('/outputs/').pop()! : norm;
  return buildUrl(`/api/v1/outputs/file?path=${encodeURIComponent(rel)}`);
}

export function Console() {
  const { 
    console: consoleEntries, 
    currentStepIndex, 
    lastFileByStep,
    lastSavedFile,
    latestState,
    messages,
    currentConversationId,
    currentToolName,
    graph
  } = useApp() as any;
  const nextIdRef = useRef<number>(3);
  const allocId = () => (nextIdRef.current += 1);
  const [lines, setLines] = useState<TerminalLine[]>([
    { id: 1, content: "Genesis Terminal v1.0.0", type: 'output', timestamp: new Date() },
    { id: 2, content: "Ready for execution...", type: 'output', timestamp: new Date() },
  ]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [stepLogLines, setStepLogLines] = useState<TerminalLine[]>([]);

  // Auto-scroll to bottom when new lines are added
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines]);

  // Live update from WS entries
  useEffect(() => {
    let cancelled = false;
    async function expandAndAppend() {
      try { console.log('[Console] Incoming entries:', consoleEntries); } catch {}
      const expanded: TerminalLine[] = [];
      for (const e of consoleEntries) {
        const type: TerminalLine['type'] = e.type === 'stderr' ? 'error' : 'output';
        const ts = new Date(e.timestamp);
        const line = String(e.line || "");
        const match = line.match(/(?:^|\s)(outputs\/[\w\-\/\.]+\.(?:txt|log))(?:\s|$)/i);
        if (match) {
          const rel = match[1];
          try { console.log('[Console] Expanding referenced file in line:', rel); } catch {}
          try {
            const url = resolveOutputUrl(rel);
            const res = await fetch(url);
            if (res.ok) {
              const text = await res.text();
              const header: TerminalLine = { id: allocId(), content: `--- ${rel} ---`, type: 'output', timestamp: ts };
              expanded.push(header);
              text.split(/\r?\n/).forEach((ln) => {
                if (ln.trim().length === 0) return;
                expanded.push({ id: allocId(), content: ln, type, timestamp: ts });
              });
              continue;
            }
          } catch {
            // fall through to raw line
          }
        }
        // Only push stdout lines; record if stderr encountered
        if (type === 'output') {
          expanded.push({ id: allocId(), content: line, type, timestamp: ts });
        } else {
          expanded.push({ id: allocId(), content: line, type: 'error', timestamp: ts });
        }
      }
      if (!cancelled) {
        setLines(prev => {
          const header = prev.slice(0, 2);
          return [...header, ...expanded.slice(-10000)];
        });
        try { console.log('[Console] Updated lines count:', expanded.length); } catch {}
      }
    }
    expandAndAppend();
    return () => { cancelled = true; };
  }, [consoleEntries]);

  // Load stdout/stderr content for selected step and display in console
  useEffect(() => {
    let cancelled = false;
    async function loadLogs() {
      // While live streaming is active, skip reading log files. We'll fetch logs after inactivity/reload.
      const now = Date.now();
      const hasRecentStream = consoleEntries.some((e: { timestamp: string }) => {
        const t = new Date(e.timestamp).getTime();
        return Number.isFinite(t) && (now - t) < 2000; // 2s inactivity threshold
      });
      if (hasRecentStream) {
        setStepLogLines([]);
        return;
      }
      const ids = deriveOutputsIds();
      const stepPrefix = deriveStepPrefix();
      try { console.log('[Console] Loading step logs for ids/prefix:', ids, stepPrefix); } catch {}
      if (!ids.convId || !ids.msgId) { setStepLogLines([]); return; }
      try {
        // List outputs; if empty for this assistant message, try previous assistant message id
        async function listFilesFor(msgId: string): Promise<Array<{ path: string; filename: string }>> {
          const listUrl = buildUrl(`/api/v1/outputs/${encodeURIComponent(ids.convId!)}/${encodeURIComponent(msgId)}`);
          const res = await fetch(listUrl);
          if (!res.ok) return [];
          const data = await res.json();
          return Array.isArray(data?.files) ? data.files : [];
        }
        let files: Array<{ path: string; filename: string }> = await listFilesFor(ids.msgId!);
        if (files.length === 0) {
          const assistants = Array.isArray(messages) ? [...messages].reverse().filter(m => m.role === 'assistant') : [];
          const currentIdx = assistants.findIndex(m => String(m.id) === ids.msgId);
          const prevMsgId = currentIdx >= 0 && assistants[currentIdx + 1]?.id ? String(assistants[currentIdx + 1].id) : undefined;
          if (prevMsgId) {
            try { console.log('[Console] Trying previous assistant msgId for logs:', prevMsgId); } catch {}
            files = await listFilesFor(prevMsgId);
          }
          // Numeric fallback: try msgId-1..-3 if still empty
          if (files.length === 0) {
            const n = Number(ids.msgId);
            if (!Number.isNaN(n)) {
              for (let back = 1; back <= 3; back++) {
                const tryId = String(n - back);
                try { console.log('[Console] Trying numeric fallback msgId for logs:', tryId); } catch {}
                const alt = await listFilesFor(tryId);
                if (alt.length > 0) { files = alt; break; }
              }
            }
          }
        }
        try { console.log('[Console] Files for logs:', files.map(f => f.filename)); } catch {}
        const byScore = (suffix: 'stdout.log' | 'stderr.log') => {
          const target = suffix.toLowerCase();
          const score = (name: string) => {
            const n = name.toLowerCase();
            if (stepPrefix && n === `${stepPrefix.toLowerCase()}_${target}`) return 3;
            if (stepPrefix && n.startsWith(`${stepPrefix.toLowerCase()}_`) && n.endsWith(target)) return 2;
            if (n.endsWith(target)) return 1;
            return 0;
          };
          const best = [...files]
            .filter(f => score(f.filename) > 0)
            .sort((a, b) => score(b.filename) - score(a.filename))[0];
          return best?.path;
        };
        const stdoutPath = byScore('stdout.log');
        const stderrPath = byScore('stderr.log');
        try { console.log('[Console] Picked logs:', { stdoutPath, stderrPath }); } catch {}
        const fetched: TerminalLine[] = [];
        async function fetchLog(path: string, type: TerminalLine['type']) {
          const url = resolveOutputUrl(path);
          const res = await fetch(url);
          if (!res.ok) return;
          const text = await res.text();
          const lines = text.split(/\r?\n/).filter(Boolean);
          const now = new Date();
          fetched.push({ id: allocId(), content: `--- ${path.split('/').pop()} ---`, type: 'output', timestamp: now });
          lines.forEach((ln) => fetched.push({ id: allocId(), content: ln, type, timestamp: now }));
        }
        // Only show stdout unless live stderr exists; if no stdout and have stderr, show stderr
        const hasLiveStderr = consoleEntries.some((e: { type: string }) => e.type === 'stderr');
        if (hasLiveStderr) {
          if (stderrPath) await fetchLog(stderrPath, 'error');
        } else {
          if (stdoutPath) await fetchLog(stdoutPath, 'output');
          else if (stderrPath) await fetchLog(stderrPath, 'error');
        }
        if (!cancelled) setStepLogLines(fetched);
      } catch {
        if (!cancelled) setStepLogLines([]);
      }
    }
    loadLogs();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStepIndex, lastFileByStep, lastSavedFile, latestState, messages, currentConversationId, currentToolName, graph, consoleEntries]);

  // Extract convId and msgId from various sources
  function deriveOutputsIds(): { convId?: string; msgId?: string } {
    // 1) From per-step saved file
    if (typeof currentStepIndex === 'number' && lastFileByStep && lastFileByStep[currentStepIndex]?.path) {
      const p = String(lastFileByStep[currentStepIndex].path).replace(/\\/g, '/');
      const parts = p.split('/');
      const i = parts.lastIndexOf('outputs');
      if (i >= 0 && parts[i + 1] && parts[i + 2]) return { convId: parts[i + 1], msgId: parts[i + 2] };
    }
    // 2) From lastSavedFile
    if (lastSavedFile?.path) {
      const p = String(lastSavedFile.path).replace(/\\/g, '/');
      const parts = p.split('/');
      const i = parts.lastIndexOf('outputs');
      if (i >= 0 && parts[i + 1] && parts[i + 2]) return { convId: parts[i + 1], msgId: parts[i + 2] };
    }
    // 3) From latestState.execution_output_path
    const execPath = (latestState as any)?.execution_output_path as string | undefined;
    if (execPath) {
      const p = String(execPath).replace(/\\/g, '/');
      const parts = p.split('/');
      const i = parts.lastIndexOf('outputs');
      if (i >= 0 && parts[i + 1] && parts[i + 2]) return { convId: parts[i + 1], msgId: parts[i + 2] };
    }
    // 4) Fallback: use current conversation id and the last assistant message id
    const lastAssistant = Array.isArray(messages) ? [...messages].reverse().find(m => m.role === 'assistant') : undefined;
    const msgId = lastAssistant?.id ? String(lastAssistant.id) : undefined;
    return { convId: currentConversationId, msgId };
  }

  function deriveStepPrefix(): string | undefined {
    // Prefer actual filename pattern if we have a file
    const f = (typeof currentStepIndex === 'number' && lastFileByStep) ? lastFileByStep[currentStepIndex] : undefined;
    const candidate = f?.path ? String(f.path).replace(/\\/g, '/').split('/').pop() : undefined;
    if (candidate) {
      const m = candidate.match(/^(\d+_[^\.]+)/);
      if (m) return m[1];
    }
    // Otherwise build from step index and tool name
    let tool = currentToolName as string | undefined;
    if (!tool && typeof currentStepIndex === 'number' && Array.isArray(graph?.chosenPath)) {
      const nid = graph.chosenPath[currentStepIndex];
      if (nid && !/_IN$|_OUT$/i.test(nid)) tool = nid;
    }
    if (typeof currentStepIndex === 'number' && tool) {
      const num = String(currentStepIndex).padStart(2, '0');
      return `${num}_${tool}`;
    }
    return undefined;
  }

  // Inject quick links to stdout/stderr for the selected step if available or derivable
  const logLinks: Array<{ label: string; url: string }> = (() => {
    const links: Array<{ label: string; url: string }> = [];
    const ids = deriveOutputsIds();
    const stepPrefix = deriveStepPrefix();
    if (ids.convId && ids.msgId && stepPrefix) {
      const stdoutRel = `outputs/${ids.convId}/${ids.msgId}/${stepPrefix}_stdout.log`;
      const stderrRel = `outputs/${ids.convId}/${ids.msgId}/${stepPrefix}_stderr.log`;
      links.push({ label: `@${stepPrefix}_stdout.log`, url: resolveOutputUrl(stdoutRel) });
      links.push({ label: `@${stepPrefix}_stderr.log`, url: resolveOutputUrl(stderrRel) });
    }
    return links;
  })();

  const getLineColor = (type: TerminalLine['type']) => {
    switch (type) {
      case 'error': return 'text-red-400';
      case 'input': return 'text-blue-400';
      default: return 'text-gray-300';
    }
  };

  const getLinePrefix = (type: TerminalLine['type']) => {
    switch (type) {
      case 'input': return '> ';
      case 'error': return '! ';
      default: return '  ';
    }
  };

  return (
    <div className="h-full bg-black rounded-lg overflow-hidden border border-gray-200">
      <div 
        ref={scrollRef}
        className="h-full overflow-auto p-4 font-mono text-sm"
      >
        {/* Step logs content */}
        {stepLogLines.map((line) => (
          <div key={line.id} className={`mb-1 ${getLineColor(line.type)}`}>
            <span className="text-gray-500">{getLinePrefix(line.type)}</span>
            {line.content}
          </div>
        ))}
        {lines.map((line) => (
          <div key={line.id} className={`mb-1 ${getLineColor(line.type)}`}>
            <span className="text-gray-500">
              {getLinePrefix(line.type)}
            </span>
            {line.content}
          </div>
        ))}
        
        {/* Blinking cursor */}
        <div className="inline-block w-2 h-4 bg-gray-400 animate-pulse ml-2"></div>
      </div>
    </div>
  );
}
