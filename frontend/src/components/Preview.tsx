"use client";
import React, { useState } from "react";
import { useApp } from "@/lib/state/AppContext";
import { buildUrl } from "@/lib/api/config";

// Reuse the same URL resolution logic as MessageBubble
function resolveFileUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  const norm = path.replace(/\\/g, "/");
  // Handle both absolute and relative outputs paths ("/outputs/..." or "outputs/...")
  if (/(^|\/)outputs\//i.test(norm)) {
    let rel = norm.replace(/^outputs\//i, "");
    if (rel.includes('/outputs/')) rel = rel.split(/\/outputs\//i).pop() || rel;
    return buildUrl(`/api/v1/outputs/file?path=${encodeURIComponent(rel)}`);
  }
  // Fallback (rare in preview): just return as-is
  return path;
}

type PreviewType = 'image' | 'audio' | 'text' | 'none';

interface PreviewData {
  type: PreviewType;
  content: string;
  filename?: string;
}

export function Preview() {
  const { latestState, lastSavedFile, currentConversationId, currentStepIndex, lastFileByStep, messages, currentToolName, graph } = useApp() as any;
  const [previewData, setPreviewData] = useState<PreviewData>({ type: 'none', content: '' });
  const [textContent, setTextContent] = useState<string>("");
  const [textLoading, setTextLoading] = useState<boolean>(false);
  const [textError, setTextError] = useState<string>("");

  function deriveOutputsIds(): { convId?: string; msgId?: string } {
    // Per-step file first
    if (typeof currentStepIndex === 'number' && lastFileByStep && lastFileByStep[currentStepIndex]?.path) {
      const p = String(lastFileByStep[currentStepIndex].path).replace(/\\/g, '/');
      const parts = p.split('/');
      const i = parts.lastIndexOf('outputs');
      if (i >= 0 && parts[i + 1] && parts[i + 2]) return { convId: parts[i + 1], msgId: parts[i + 2] };
    }
    // Last saved file
    if (lastSavedFile?.path) {
      const p = String(lastSavedFile.path).replace(/\\/g, '/');
      const parts = p.split('/');
      const i = parts.lastIndexOf('outputs');
      if (i >= 0 && parts[i + 1] && parts[i + 2]) return { convId: parts[i + 1], msgId: parts[i + 2] };
    }
    // latestState.execution_output_path
    const execPath = (latestState as any)?.execution_output_path as string | undefined;
    if (execPath) {
      const p = String(execPath).replace(/\\/g, '/');
      const parts = p.split('/');
      const i = parts.lastIndexOf('outputs');
      if (i >= 0 && parts[i + 1] && parts[i + 2]) return { convId: parts[i + 1], msgId: parts[i + 2] };
    }
    // Fallback
    const lastAssistant = Array.isArray(messages) ? [...messages].reverse().find(m => m.role === 'assistant') : undefined;
    const msgId = lastAssistant?.id ? String(lastAssistant.id) : undefined;
    return { convId: currentConversationId, msgId };
  }

  function deriveStepPrefix(): string | undefined {
    const f = (typeof currentStepIndex === 'number' && lastFileByStep) ? lastFileByStep[currentStepIndex] : undefined;
    const candidate = f?.path ? String(f.path).replace(/\\/g, '/').split('/').pop() : undefined;
    if (candidate) {
      const m = candidate.match(/^(\d+_[^\.]+)/);
      if (m) return m[1];
    }
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

  React.useEffect(() => {
    // Prefer live file_saved event
    if (currentConversationId) {
      // If a step is selected, try that step's latest file first
      if (typeof currentStepIndex === 'number' && lastFileByStep && lastFileByStep[currentStepIndex]) {
        const f = lastFileByStep[currentStepIndex];
        try { console.log('[Preview] Using lastFileByStep for step', currentStepIndex, '->', f); } catch {}
        const url = resolveFileUrl(String(f.path));
        const name = String(f.path).replace(/\\/g, '/').split('/').pop();
        const mime = f.mime || '';
        if (mime.startsWith('image/')) setPreviewData({ type: 'image', content: url, filename: name });
        else if (mime.startsWith('audio/')) setPreviewData({ type: 'audio', content: url, filename: name });
        else setPreviewData({ type: 'text', content: url, filename: name });
        return;
      }
      // Otherwise list outputs for the derived ids and choose best preview by step_index/tool
      const ids = deriveOutputsIds();
      if (ids.convId && ids.msgId) {
        (async () => {
          try {
            const idx = typeof currentStepIndex === 'number' ? currentStepIndex + 1 : undefined;
            const tool = typeof currentToolName === 'string' ? currentToolName : undefined;
            try { console.log('[Preview] Listing outputs for', ids, { idx, tool }); } catch {}
            const listUrl = buildUrl(`/api/v1/outputs/${encodeURIComponent(ids.convId!)}/${encodeURIComponent(ids.msgId!)}`);
            const listRes = await fetch(listUrl);
            if (listRes.ok) {
              const data = await listRes.json();
              const files: Array<{ path: string; filename: string; mime_type?: string }> = Array.isArray(data?.files) ? data.files : [];
              const pad = (n: number) => String(n).padStart(2, '0');
              // Use zero-based step_index per spec (no +1)
              const primaryPrefix = (typeof currentStepIndex === 'number' && tool) ? `${pad(currentStepIndex)}_${tool}`.toLowerCase() : undefined;
              const altPrefix = (typeof currentStepIndex === 'number') ? `${pad(currentStepIndex)}_` : undefined;
              try { console.log('[Preview] Files returned:', files.map(f => f.filename)); } catch {}
              try { console.log('[Preview] Prefixes:', { primaryPrefix, altPrefix }); } catch {}
              const isLog = (name: string) => /_(stdout|stderr)\.log$/i.test(name);
              const prefRank = (f: { filename: string }) => {
                const name = f.filename.toLowerCase();
                if (primaryPrefix && name.startsWith(primaryPrefix) && !isLog(name)) return 3;
                if (altPrefix && name.startsWith(altPrefix) && !isLog(name)) return 2;
                if (!isLog(name)) return 1;
                return 0;
              };
              const best = [...files]
                .filter(f => prefRank(f) > 0)
                .sort((a, b) => prefRank(b) - prefRank(a))
                [0];
              if (best) {
                const url = resolveFileUrl(`outputs/${best.path.replace(/^outputs\//i, '')}`);
                const name = best.filename;
                const lower = name.toLowerCase();
                try { console.log('[Preview] Selected preview:', { name, url }); } catch {}
                if (/(\.png|\.jpg|\.jpeg|\.gif|\.webp)$/i.test(lower)) {
                  setPreviewData({ type: 'image', content: url, filename: name });
                  return;
                }
                if (/(\.mp3|\.wav|\.m4a|\.ogg)$/i.test(lower)) {
                  setPreviewData({ type: 'audio', content: url, filename: name });
                  return;
                }
                setPreviewData({ type: 'text', content: url, filename: name });
                return;
              }
              try { console.log('[Preview] No matching preview artifact found'); } catch {}
              // If no files found for this assistant message, heuristically try the previous assistant message id
              const prevAssistant = Array.isArray(messages) ? [...messages].reverse().filter(m => m.role === 'assistant') : [];
              const currentIdx = prevAssistant.findIndex(m => String(m.id) === ids.msgId);
              const prevMsgId = currentIdx >= 0 && prevAssistant[currentIdx + 1]?.id ? String(prevAssistant[currentIdx + 1].id) : undefined;
              if (prevMsgId) {
                try { console.log('[Preview] Trying previous assistant msgId for outputs:', prevMsgId); } catch {}
                const altListUrl = buildUrl(`/api/v1/outputs/${encodeURIComponent(ids.convId!)}/${encodeURIComponent(prevMsgId)}`);
                const altRes = await fetch(altListUrl);
                if (altRes.ok) {
                  const altData = await altRes.json();
                  const altFiles: Array<{ path: string; filename: string; mime_type?: string }> = Array.isArray(altData?.files) ? altData.files : [];
                  const bestAlt = altFiles.find(f => primaryPrefix ? f.filename.toLowerCase().startsWith(primaryPrefix) : true);
                  if (bestAlt) {
                    const altUrl = resolveFileUrl(`outputs/${bestAlt.path.replace(/^outputs\//i, '')}`);
                    const lower = bestAlt.filename.toLowerCase();
                    if (/(\.png|\.jpg|\.jpeg|\.gif|\.webp)$/i.test(lower)) { setPreviewData({ type: 'image', content: altUrl, filename: bestAlt.filename }); return; }
                    if (/(\.mp3|\.wav|\.m4a|\.ogg)$/i.test(lower)) { setPreviewData({ type: 'audio', content: altUrl, filename: bestAlt.filename }); return; }
                    setPreviewData({ type: 'text', content: altUrl, filename: bestAlt.filename });
                    return;
                  }
                }
              }
              // Numeric fallback: try msgId-1..-3 if numeric
              const n = Number(ids.msgId);
              if (!Number.isNaN(n)) {
                for (let back = 1; back <= 3; back++) {
                  const tryId = String(n - back);
                  try { console.log('[Preview] Trying numeric fallback msgId for outputs:', tryId); } catch {}
                  const altListUrl2 = buildUrl(`/api/v1/outputs/${encodeURIComponent(ids.convId!)}/${encodeURIComponent(tryId)}`);
                  const altRes2 = await fetch(altListUrl2);
                  if (altRes2.ok) {
                    const altData2 = await altRes2.json();
                    const altFiles2: Array<{ path: string; filename: string; mime_type?: string }> = Array.isArray(altData2?.files) ? altData2.files : [];
                    const bestAlt2 = altFiles2.find(f => primaryPrefix ? f.filename.toLowerCase().startsWith(primaryPrefix) : true) || altFiles2.find(f => !/_stdout\.log$|_stderr\.log$/i.test(f.filename));
                    if (bestAlt2) {
                      const altUrl2 = resolveFileUrl(`outputs/${bestAlt2.path.replace(/^outputs\//i, '')}`);
                      const lower2 = bestAlt2.filename.toLowerCase();
                      if (/(\.png|\.jpg|\.jpeg|\.gif|\.webp)$/i.test(lower2)) { setPreviewData({ type: 'image', content: altUrl2, filename: bestAlt2.filename }); return; }
                      if (/(\.mp3|\.wav|\.m4a|\.ogg)$/i.test(lower2)) { setPreviewData({ type: 'audio', content: altUrl2, filename: bestAlt2.filename }); return; }
                      setPreviewData({ type: 'text', content: altUrl2, filename: bestAlt2.filename });
                      return;
                    }
                  }
                }
              }
            }
          } catch {
            // ignore
          }
        })();
      }
      // Fallback to the most recent saved file
      if (lastSavedFile && typeof lastSavedFile.path === 'string') {
        const url = resolveFileUrl(String(lastSavedFile.path));
        const name = String(lastSavedFile.path).replace(/\\/g, '/').split('/').pop();
        const mime = lastSavedFile.mime || '';
        if (mime.startsWith('image/')) setPreviewData({ type: 'image', content: url, filename: name });
        else if (mime.startsWith('audio/')) setPreviewData({ type: 'audio', content: url, filename: name });
        else setPreviewData({ type: 'text', content: url, filename: name });
        return;
      }
    }
    // Fallback to state.execution_output_path if present
    const execPath = (latestState as any)?.execution_output_path as string | undefined;
    if (execPath) {
      const url = resolveFileUrl(String(execPath));
      const name = String(execPath).replace(/\\/g, '/').split('/').pop();
      // Guess by extension
      if (/\.(png|jpg|jpeg|gif|webp)$/i.test(String(execPath))) setPreviewData({ type: 'image', content: url, filename: name });
      else if (/\.(mp3|wav|m4a|ogg)$/i.test(String(execPath))) setPreviewData({ type: 'audio', content: url, filename: name });
      else setPreviewData({ type: 'text', content: url, filename: name });
      return;
    }
    setPreviewData({ type: 'none', content: '' });
  }, [lastSavedFile, latestState, currentConversationId, currentStepIndex, lastFileByStep]);

  // If text preview, fetch and render the text contents
  React.useEffect(() => {
    let cancelled = false;
    async function fetchText() {
      if (previewData.type !== 'text' || !previewData.content) { setTextContent(""); setTextError(""); setTextLoading(false); return; }
      setTextLoading(true);
      setTextError("");
      try {
        try { console.log('[Preview] Fetching text:', previewData); } catch {}
        const res = await fetch(previewData.content);
        if (res.status === 404) {
          // Fallback: if we derived .txt but it doesn't exist, try listing and picking any .txt for the step
          const ids = deriveOutputsIds();
          const prefix = deriveStepPrefix();
          if (ids.convId && ids.msgId) {
            const listUrl = buildUrl(`/api/v1/outputs/${encodeURIComponent(ids.convId)}/${encodeURIComponent(ids.msgId)}`);
            const listRes = await fetch(listUrl);
            if (listRes.ok) {
              const data = await listRes.json();
              const files: Array<{ path: string; filename: string }> = Array.isArray(data?.files) ? data.files : [];
              const pick = () => {
                if (prefix) {
                  const exact = files.find(f => f.filename.toLowerCase() === `${prefix.toLowerCase()}.txt`);
                  if (exact) return exact.path;
                }
                return files.find(f => /\.txt$/i.test(f.filename))?.path;
              };
              const candidate = pick();
              if (candidate) {
                const url = resolveFileUrl(candidate);
                try { console.log('[Preview] Text 404 fallback picked:', candidate, '->', url); } catch {}
                setPreviewData(prev => ({ ...prev, content: url, filename: candidate.split('/').pop() }));
                return; // Will re-trigger effect and fetch
              }
              try { console.log('[Preview] Text 404 fallback: no .txt found'); } catch {}
            }
          }
          setTextContent("");
          setTextError("Text file not found");
          setTextLoading(false);
          return;
        }
        if (!res.ok) { setTextContent(""); setTextError(`Failed to load (${res.status})`); setTextLoading(false); return; }
        const txt = await res.text();
        if (!cancelled) { setTextContent(txt); setTextLoading(false); try { console.log('[Preview] Text loaded:', (previewData.filename || previewData.content)); } catch {} }
      } catch {
        if (!cancelled) { setTextContent(""); setTextError("Failed to load text"); setTextLoading(false); try { console.log('[Preview] Text load failed:', previewData); } catch {} }
      }
    }
    fetchText();
    return () => { cancelled = true; };
  }, [previewData]);

  const renderPreview = () => {
    switch (previewData.type) {
      case 'image':
        return (
          <div className="w-full h-full flex items-center justify-center bg-gray-50">
            <div className="w-full h-full">
              <img 
                src={previewData.content} 
                alt="Preview"
                className="w-full h-full object-contain"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = 'none';
                }}
              />
            </div>
          </div>
        );
      
      case 'audio':
        return (
          <div className="w-full h-full flex items-center justify-center bg-gray-50">
            <div className="text-center">
              <div className="text-6xl mb-4">🎵</div>
              <audio controls className="mb-2">
                <source src={previewData.content} type="audio/mpeg" />
                Your browser does not support the audio element.
              </audio>
              <div className="text-sm text-gray-600">{previewData.filename}</div>
            </div>
          </div>
        );
      
      case 'text':
        return (
          <div className="w-full h-full p-4 bg-white overflow-auto">
            {textLoading ? (
              <div className="text-sm text-gray-500">Loading text…</div>
            ) : textError ? (
              <div className="text-sm text-red-600">{textError}</div>
            ) : (
            <pre className="whitespace-pre-wrap text-sm text-gray-800">
                {textContent}
            </pre>
            )}
          </div>
        );
      
      default:
        return (
          <div className="w-full h-full flex items-center justify-center bg-gray-50">
            <div className="text-center text-gray-500">
              <div className="text-4xl mb-2">📄</div>
              <div className="text-sm">No Preview Available</div>
              <div className="text-xs mt-1">Output will appear here</div>
            </div>
          </div>
        );
    }
  };

  return (
    <div className="h-full bg-white rounded-lg overflow-hidden border border-gray-200">
      <div className="flex items-center justify-between p-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
          <span className="text-sm font-medium text-gray-700">Preview</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">{previewData.type}</span>
          {previewData.filename && (
            <span className="text-xs text-gray-400">• {previewData.filename}</span>
          )}
        </div>
      </div>
      
      <div className="h-full overflow-hidden">
        {renderPreview()}
      </div>
    </div>
  );
}
