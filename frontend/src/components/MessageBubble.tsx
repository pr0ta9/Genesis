"use client";

import React, { useEffect, useRef, useState } from "react";
import { MessageResponse } from "@/lib/api/types";
import { Reasoning } from "./Reasoning";
import { useApp } from "@/lib/state/AppContext";
import { buildUrl, ENDPOINTS } from "@/lib/api/config";
import AudioPlayer from "@/components/AudioPlayer";

interface MessageBubbleProps {
  message: MessageResponse;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);
  const [userCopyPinned, setUserCopyPinned] = useState(false);
  const [userHover, setUserHover] = useState(false);
  const userRef = useRef<HTMLDivElement | null>(null);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const { currentConversationId } = (useApp() as any) || {};

  // Extract <file>...</file> tags from assistant content
  function extractFileTags(text: string | undefined): string[] {
    if (!text) return [];
    const regex = /<file>([\s\S]*?)<\/file>/gi;
    const files: string[] = [];
    let match: RegExpExecArray | null;
    while ((match = regex.exec(text)) !== null) {
      const p = (match[1] || "").trim();
      if (p) files.push(p);
    }
    return files;
  }

  function getFileName(path: string): string {
    const norm = path.replace(/\\/g, "/");
    const parts = norm.split("/");
    return parts[parts.length - 1] || path;
  }

  function resolveFileUrl(path: string): string {
    // If it's already a URL, return as-is
    if (/^https?:\/\//i.test(path)) return path;
    const norm = path.replace(/\\/g, "/");
    // If this is an absolute outputs path, stream via outputs API with full path
    if (/\/outputs\//i.test(norm)) {
      const rel = norm.split(/\/outputs\//i).pop() || norm;
      return buildUrl(`/api/v1/outputs/file?path=${encodeURIComponent(rel)}`);
    }
    // Otherwise assume inputs upload served by uploads API: convId/filename
    const parts = norm.split("/");
    if (parts.length >= 2) {
      const convId = parts[parts.length - 2];
      const filename = parts[parts.length - 1];
      return `${buildUrl(ENDPOINTS.uploads)}/${encodeURIComponent(convId)}/${encodeURIComponent(filename)}`;
    }
    return path;
  }

  function isImagePath(path: string): boolean {
    const name = getFileName(path).toLowerCase();
    return (
      name.endsWith(".png") ||
      name.endsWith(".jpg") ||
      name.endsWith(".jpeg") ||
      name.endsWith(".gif") ||
      name.endsWith(".webp")
    );
  }

  function isAudioPath(path: string): boolean {
    const name = getFileName(path).toLowerCase();
    return (
      name.endsWith(".mp3") ||
      name.endsWith(".wav") ||
      name.endsWith(".m4a") ||
      name.endsWith(".ogg") ||
      name.endsWith(".webm") ||
      name.endsWith(".flac")
    );
  }

  function renderContentWithFileLinks(text: string | undefined) {
    if (!text) return null;
    const regex = /<file>([\s\S]*?)<\/file>/gi;
    const nodes: Array<string | React.ReactNode> = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = regex.exec(text)) !== null) {
      const start = match.index;
      const end = regex.lastIndex;
      const before = text.slice(lastIndex, start);
      if (before) nodes.push(before);
      const rawPath = (match[1] || "").trim();
      if (rawPath) {
        const url = resolveFileUrl(rawPath);
        const label = getFileName(rawPath);
        nodes.push(
          <a
            key={`${start}-${end}`}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 underline break-all"
          >
            {label}
          </a>
        );
      }
      lastIndex = end;
    }
    const tail = text.slice(lastIndex);
    if (tail) nodes.push(tail);
    return nodes;
  }

  function filterAssistantContentForClarification(raw: string | undefined): string {
    if (!raw) return '';
    const base = String(raw).trim();
    const workflow = (message as any)?.workflow;
    if (!workflow || !Array.isArray(workflow.sections)) return base;
    const clarifications: string[] = workflow.sections
      .map((s: any) => (typeof s?.clarification === 'string' ? s.clarification.trim() : ''))
      .filter(Boolean);
    // If the main content is exactly the clarification (plain), hide it (keep the ❓ version visible)
    for (const c of clarifications) {
      if (base === c) {
        return '';
      }
    }
    return base;
  }

  function StageRow({ section }: { section: any }) {
    const [open, setOpen] = useState(false);
    const seconds = Number(section?.thinking_time || 0);
    const secondsText = Number.isFinite(seconds) ? (Math.round(seconds * 10) / 10).toFixed(1) : "0.0";
    const hasReasoning = typeof section?.reasoning_content === 'string' && section.reasoning_content.trim().length > 0;
    return (
      <div>
        {/* Title line (swap size with thought label) */}
        <div className="text-xs text-gray-700 " style={{ fontSize: 15 , fontWeight: "bold"}}>
          {section?.title}
        </div>
        {/* Thought toggle line (collapsible) */}
        {hasReasoning && (
          <div className="pl-2">
            <button
              type="button"
              className="text-sm text-gray-700 hover:underline"
              onClick={() => setOpen(!open)}
            >
              Thought for {secondsText}s
            </button>
            {open && (
              <div className="mt-1 border-l-2 border-gray-200 pl-3 ml-1 max-w-full">
                <div className="leading-relaxed whitespace-pre-wrap break-words select-text overflow-x-auto max-w-full" style={{ fontSize: 12 }}>
                  {section.reasoning_content}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  async function handleAssistantCopy() {
    try {
      await navigator.clipboard.writeText(message.content || "");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // no-op
    }
  }

  async function handleUserCopy() {
    try {
      await navigator.clipboard.writeText(message.content || "");
      setCopied(true);
      setUserCopyPinned(true);
      // Keep check visible briefly; button remains due to pinned until outside click
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // no-op
    }
  }

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!userCopyPinned) return;
      const el = userRef.current;
      if (!el) return;
      if (e.target instanceof Node && el.contains(e.target)) return;
      setUserCopyPinned(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [userCopyPinned]);
  if (message.role === "user") {
    // Derive attachments from saved references if not present (survive refresh)
    const refs: string[] = Array.isArray((message as any)?.reasoning?.additional_kwargs?.file_references)
      ? (message as any).reasoning.additional_kwargs.file_references
      : [];
    const derivedAttachments = (!Array.isArray(message.attachments) || message.attachments.length === 0) && currentConversationId
      ? refs.map((ref) => {
          const name = String(ref);
          const lower = name.toLowerCase();
          const isImg = /(\.png|\.jpg|\.jpeg|\.gif|\.webp)$/.test(lower);
          const isAudio = /(\.mp3|\.wav|\.m4a|\.ogg|\.webm|\.flac)$/.test(lower);
          const mime = isImg ? "image/*" : isAudio ? "audio/*" : "application/octet-stream";
          const url = `${buildUrl(ENDPOINTS.uploads)}/${encodeURIComponent(currentConversationId)}/${encodeURIComponent(name)}`;
          return { name, mime, url };
        })
      : [];
    const attachmentsToRender = (Array.isArray(message.attachments) && message.attachments.length > 0)
      ? message.attachments
      : derivedAttachments;
    const hasAttachments = Array.isArray(attachmentsToRender) && attachmentsToRender.length > 0;
    const hasText = typeof message.content === 'string' && message.content.trim().length > 0;
    const bubbleClass = hasAttachments && !hasText
      ? "w-full bg-transparent text-gray-900 rounded-2xl p-0"
      : "w-full bg-gray-100 text-gray-900 rounded-2xl px-4 py-3";
    return (
      <div className="flex justify-end">
        <div
          ref={userRef}
          className="max-w-[85%] flex flex-col items-end"
          onMouseEnter={() => setUserHover(true)}
          onMouseLeave={() => setUserHover(false)}
        >
          <div className={bubbleClass}>
            {/* Attachments preview */}
            {hasAttachments && (
              <div className={`flex flex-col gap-2 ${hasText ? 'mb-2' : ''}`}>
                {attachmentsToRender!.map((att: any, idx: number) => {
                  const isImg = att.mime?.startsWith('image/');
                  const isAudio = att.mime?.startsWith('audio/');
                  const isVideo = att.mime?.startsWith('video/');
                  return (
                    <div key={idx} className="rounded-xl ">
                      {isImg && (
                        <img
                          src={att.url}
                          alt={att.name}
                          className="max-h-64 w-auto object-contain cursor-zoom-in"
                          onClick={() => setLightboxUrl(att.url)}
                        />
                      )}
                      {isAudio && (
                        <>
                          <AudioPlayer src={att.url} filename={att.name} />
                          <style jsx>{`
                            audio.audio-clean { background: transparent; outline: none; }
                            audio.audio-clean::-webkit-media-controls-enclosure { background: transparent !important; box-shadow: none !important; }
                            audio.audio-clean::-webkit-media-controls-panel { background: transparent !important; }
                            /* Try to position overflow menus below/right when possible */
                            audio.audio-clean::-webkit-media-controls-overlay-play-button { margin-left: auto; }
                          `}</style>
                        </>
                      )}
                      {isVideo && (
                        <video src={att.url} controls className="max-h-64 w-auto" />
                      )}
                      {!isImg && !isAudio && !isVideo && (
                        <div className="p-3 text-sm text-gray-600 truncate">{att.name}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
            {hasText && (
              <div className="text-base leading-relaxed whitespace-pre-wrap break-words select-text">
                {message.content}
              </div>
            )}
          </div>
          <div className={`mt-1 ${userCopyPinned || userHover ? "opacity-100" : "opacity-0"} transition-opacity`}> 
            <button
              className="inline-flex items-center justify-center w-7 h-7 rounded hover:bg-gray-200"
              aria-label="Copy message"
              onClick={handleUserCopy}
              title="Copy"
            >
              {copied ? (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg" className="text-black-600">
                  <path d="M6.00016 10.2002L3.80016 8.0002L2.86683 8.93353L6.00016 12.0669L14.0002 4.06686L13.0668 3.13353L6.00016 10.2002Z"></path>
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" className="text-gray-600">
                  <path d="M6.14926 4.02039C7.11194 4.02039 7.8798 4.02023 8.49594 4.07605C9.12125 4.13276 9.65789 4.25194 10.1414 4.53113C10.7201 4.86536 11.2008 5.34597 11.535 5.92468C11.8142 6.40824 11.9334 6.94488 11.9901 7.57019C12.0459 8.18631 12.0457 8.95426 12.0457 9.91687C12.0457 10.8795 12.0459 11.6474 11.9901 12.2635C11.9334 12.8889 11.8142 13.4255 11.535 13.9091C11.2008 14.4877 10.7201 14.9684 10.1414 15.3026C9.65789 15.5818 9.12125 15.701 8.49594 15.7577C7.87981 15.8135 7.11193 15.8134 6.14926 15.8134C5.18664 15.8134 4.41871 15.8135 3.80258 15.7577C3.17727 15.701 2.64063 15.5818 2.15707 15.3026C1.57837 14.9684 1.09775 14.4877 0.763519 13.9091C0.484335 13.4255 0.365153 12.8889 0.308441 12.2635C0.252618 11.6474 0.252777 10.8795 0.252777 9.91687C0.252777 8.95425 0.252634 8.18632 0.308441 7.57019C0.365153 6.94488 0.484335 6.40824 0.763519 5.92468C1.09774 5.34596 1.57836 4.86535 2.15707 4.53113C2.64063 4.25194 3.17727 4.13276 3.80258 4.07605C4.41871 4.02024 5.18663 4.02039 6.14926 4.02039ZM6.14926 5.37781C5.16178 5.37781 4.46631 5.37768 3.92563 5.42664C3.39431 5.47479 3.07856 5.5658 2.83578 5.70593C2.46317 5.92112 2.15351 6.23077 1.93832 6.60339C1.7982 6.84617 1.70718 7.16192 1.65903 7.69324C1.61007 8.23391 1.6102 8.9294 1.6102 9.91687C1.6102 10.9044 1.61006 11.5998 1.65903 12.1405C1.70718 12.6718 1.7982 12.9876 1.93832 13.2303C2.15352 13.6029 2.46318 13.9126 2.83578 14.1278C3.07856 14.2679 3.39431 14.3589 3.92563 14.4071C4.46631 14.4561 5.16179 14.4559 6.14926 14.4559C7.13679 14.4559 7.83221 14.4561 8.37289 14.4071C8.90422 14.3589 9.21996 14.2679 9.46274 14.1278C9.83532 13.9126 10.145 13.6029 10.3602 13.2303C10.5003 12.9876 10.5913 12.6718 10.6395 12.1405C10.6885 11.5998 10.6883 10.9044 10.6883 9.91687C10.6883 8.92941 10.6885 8.23391 10.6395 7.69324C10.5913 7.16192 10.5003 6.84617 10.3602 6.60339C10.145 6.23078 9.83533 5.92113 9.46274 5.70593C9.21996 5.5658 8.90421 5.47479 8.37289 5.42664C7.83221 5.37766 7.13679 5.37781 6.14926 5.37781ZM9.80161 0.368042C10.7638 0.368042 11.5314 0.367947 12.1473 0.423706C12.7725 0.480374 13.3093 0.598826 13.7928 0.877808C14.3716 1.21198 14.8521 1.69361 15.1864 2.27234C15.4655 2.75581 15.5857 3.29171 15.6424 3.91687C15.6983 4.53307 15.6971 5.30167 15.6971 6.26453V7.82996C15.6971 8.29271 15.6989 8.59 15.6649 8.84851C15.4668 10.3526 14.4009 11.5739 12.9832 11.9989V10.5468C13.6973 10.1904 14.2104 9.49669 14.3192 8.67175C14.3387 8.52354 14.3407 8.33586 14.3407 7.82996V6.26453C14.3407 5.27713 14.3398 4.58155 14.2909 4.04089C14.2427 3.50975 14.1526 3.19379 14.0125 2.95105C13.7974 2.57856 13.4875 2.26876 13.1151 2.05359C12.8723 1.91353 12.5564 1.82244 12.0252 1.77429C11.4847 1.72534 10.7888 1.72546 9.80161 1.72546H7.71469C6.75617 1.72565 5.92662 2.27704 5.52328 3.07898H4.07016C4.54218 1.51138 5.99317 0.368253 7.71469 0.368042H9.80161Z" fill="currentColor"/>
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Assistant message with reasoning support
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] text-gray-900">
        <div className="mb-6" style={{ "--assistant-last-margin-bottom": "32px" } as React.CSSProperties}>
          <div className="ds-message group">
            <div>
              {/* Reasoning Section */}
              {message.reasoning && !(message.workflow && Array.isArray(message.workflow.sections) && message.workflow.sections.length > 0) && (
                <Reasoning reasoning={message.reasoning} />
              )}

              {/* Main Message Content */}
              <div className="ds-markdown mb-4">
                {/* Workflow per-stage sections */}
                {message.workflow && Array.isArray(message.workflow.sections) && message.workflow.sections.length > 0 && (
                  <div className="mb-4 space-y-2">
                    {message.workflow.sections.map((s, idx) => (
                      <StageRow key={`${s.node}-${idx}`} section={s} />
                    ))}
                  </div>
                )}
                {/* Assistant attachments preview from <file> tags */}
                {(() => {
                  const files = extractFileTags(message.content);
                  if (!files.length) return null;
                  return (
                    <div className="flex flex-col gap-2 mb-3">
                      {files.map((p, idx) => {
                        const url = resolveFileUrl(p);
                        const isImg = isImagePath(p);
                        const isAudio = isAudioPath(p);
                        const name = getFileName(p);
                        return (
                          <div key={idx} className="rounded-xl">
                            {isImg ? (
                              <img
                                src={url}
                                alt={name}
                                className="max-h-64 w-auto object-contain cursor-zoom-in"
                                onClick={() => setLightboxUrl(url)}
                              />
                            ) : isAudio ? (
                              <AudioPlayer src={url} filename={name} />
                            ) : (
                              <a
                                href={url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="block p-3 text-sm text-blue-600 underline break-all"
                              >
                                {name}
                              </a>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                })()}

                <div className="text-base leading-relaxed whitespace-pre-wrap break-words select-text">
                  {renderContentWithFileLinks(filterAssistantContentForClarification(message.content))}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2.5">
                <div className="flex items-center gap-2.5">
                  {/* Copy Button */}
                  <button
                    className="flex items-center justify-center w-7 h-7 rounded hover:bg-gray-100"
                    aria-label="Copy message"
                    onClick={handleAssistantCopy}
                  >
                    {copied ? (
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg" className="text-black-600">
                        <path d="M6.00016 10.2002L3.80016 8.0002L2.86683 8.93353L6.00016 12.0669L14.0002 4.06686L13.0668 3.13353L6.00016 10.2002Z"></path>
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" className="text-gray-500">
                        <path d="M6.14926 4.02039C7.11194 4.02039 7.8798 4.02023 8.49594 4.07605C9.12125 4.13276 9.65789 4.25194 10.1414 4.53113C10.7201 4.86536 11.2008 5.34597 11.535 5.92468C11.8142 6.40824 11.9334 6.94488 11.9901 7.57019C12.0459 8.18631 12.0457 8.95426 12.0457 9.91687C12.0457 10.8795 12.0459 11.6474 11.9901 12.2635C11.9334 12.8889 11.8142 13.4255 11.535 13.9091C11.2008 14.4877 10.7201 14.9684 10.1414 15.3026C9.65789 15.5818 9.12125 15.701 8.49594 15.7577C7.87981 15.8135 7.11193 15.8134 6.14926 15.8134C5.18664 15.8134 4.41871 15.8135 3.80258 15.7577C3.17727 15.701 2.64063 15.5818 2.15707 15.3026C1.57837 14.9684 1.09775 14.4877 0.763519 13.9091C0.484335 13.4255 0.365153 12.8889 0.308441 12.2635C0.252618 11.6474 0.252777 10.8795 0.252777 9.91687C0.252777 8.95425 0.252634 8.18632 0.308441 7.57019C0.365153 6.94488 0.484335 6.40824 0.763519 5.92468C1.09774 5.34596 1.57836 4.86535 2.15707 4.53113C2.64063 4.25194 3.17727 4.13276 3.80258 4.07605C4.41871 4.02024 5.18663 4.02039 6.14926 4.02039ZM6.14926 5.37781C5.16178 5.37781 4.46631 5.37768 3.92563 5.42664C3.39431 5.47479 3.07856 5.5658 2.83578 5.70593C2.46317 5.92112 2.15351 6.23077 1.93832 6.60339C1.7982 6.84617 1.70718 7.16192 1.65903 7.69324C1.61007 8.23391 1.6102 8.9294 1.6102 9.91687C1.6102 10.9044 1.61006 11.5998 1.65903 12.1405C1.70718 12.6718 1.7982 12.9876 1.93832 13.2303C2.15352 13.6029 2.46318 13.9126 2.83578 14.1278C3.07856 14.2679 3.39431 14.3589 3.92563 14.4071C4.46631 14.4561 5.16179 14.4559 6.14926 14.4559C7.13679 14.4559 7.83221 14.4561 8.37289 14.4071C8.90422 14.3589 9.21996 14.2679 9.46274 14.1278C9.83532 13.9126 10.145 13.6029 10.3602 13.2303C10.5003 12.9876 10.5913 12.6718 10.6395 12.1405C10.6885 11.5998 10.6883 10.9044 10.6883 9.91687C10.6883 8.92941 10.6885 8.23391 10.6395 7.69324C10.5913 7.16192 10.5003 6.84617 10.3602 6.60339C10.145 6.23078 9.83533 5.92113 9.46274 5.70593C9.21996 5.5658 8.90421 5.47479 8.37289 5.42664C7.83221 5.37766 7.13679 5.37781 6.14926 5.37781ZM9.80161 0.368042C10.7638 0.368042 11.5314 0.367947 12.1473 0.423706C12.7725 0.480374 13.3093 0.598826 13.7928 0.877808C14.3716 1.21198 14.8521 1.69361 15.1864 2.27234C15.4655 2.75581 15.5857 3.29171 15.6424 3.91687C15.6983 4.53307 15.6971 5.30167 15.6971 6.26453V7.82996C15.6971 8.29271 15.6989 8.59 15.6649 8.84851C15.4668 10.3526 14.4009 11.5739 12.9832 11.9989V10.5468C13.6973 10.1904 14.2104 9.49669 14.3192 8.67175C14.3387 8.52354 14.3407 8.33586 14.3407 7.82996V6.26453C14.3407 5.27713 14.3398 4.58155 14.2909 4.04089C14.2427 3.50975 14.1526 3.19379 14.0125 2.95105C13.7974 2.57856 13.4875 2.26876 13.1151 2.05359C12.8723 1.91353 12.5564 1.82244 12.0252 1.77429C11.4847 1.72534 10.7888 1.72546 9.80161 1.72546H7.71469C6.75617 1.72565 5.92662 2.27704 5.52328 3.07898H4.07016C4.54218 1.51138 5.99317 0.368253 7.71469 0.368042H9.80161Z" fill="currentColor"/>
                      </svg>
                    )}
                  </button>

                  {/* Regenerate Button */}
                  <button
                    className="flex items-center justify-center w-7 h-7 rounded hover:bg-gray-100 transition-colors"
                    aria-label="Regenerate response"
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" className="text-gray-500">
                      <path d="M7.92142 0.349213C10.3745 0.349295 12.5564 1.50526 13.9558 3.299L15.1282 2.12765C15.3304 1.92552 15.6768 2.06949 15.6768 2.35544V5.53929C15.6766 5.71632 15.533 5.85982 15.356 5.86008H12.1711C11.8855 5.85976 11.7427 5.51471 11.9443 5.31255L12.9642 4.29062C11.8238 2.74311 9.98914 1.74112 7.92142 1.74104C4.46442 1.74104 1.66239 4.54307 1.66239 8.00006C1.66239 11.4571 4.46442 14.2591 7.92142 14.2591C11.3783 14.2589 14.1804 11.457 14.1804 8.00006H15.5723C15.5723 12.2252 12.1465 15.6508 7.92142 15.6509C3.6962 15.6509 0.270569 12.2253 0.270569 8.00006C0.270569 3.77485 3.6962 0.349213 7.92142 0.349213Z" fill="currentColor"/>
                    </svg>
                  </button>

                  {/* Thumbs Up */}
                  <button
                    className="flex items-center justify-center w-7 h-7 rounded hover:bg-gray-100 transition-colors"
                    aria-label="Like response"
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" className="text-gray-500">
                      <path d="M8.27861 0.811633C8.81985 0.142255 9.79016 0.0422445 10.4537 0.557662L10.5823 0.669367L10.6065 0.693605L10.6097 0.695713L10.6392 0.72522C11.3549 1.44685 11.6336 2.49474 11.3716 3.47675L11.3705 3.48097L11.361 3.5168L11.36 3.51891L10.8889 5.2261C10.8796 5.26003 10.8706 5.29164 10.8626 5.32094C10.8934 5.32101 10.927 5.322 10.9627 5.322H11.9006C12.4263 5.322 12.783 5.31906 13.0651 5.36731C14.8182 5.66725 15.9851 7.34574 15.6564 9.09363C15.6035 9.37493 15.4769 9.70926 15.2939 10.2023L14.337 12.7799C14.1401 13.3105 13.9773 13.7518 13.8101 14.1025C13.6375 14.4646 13.4385 14.7794 13.1441 15.0425C12.9712 15.197 12.7801 15.3303 12.5751 15.4387C12.2259 15.6232 11.8608 15.7 11.4612 15.7359C11.0742 15.7705 10.6034 15.7696 10.0374 15.7696H4.87371C4.08047 15.7696 3.42922 15.7703 2.90728 15.7138C2.37206 15.6558 1.88985 15.5311 1.4667 15.2237C1.22409 15.0475 1.01072 14.834 0.834405 14.5914C0.52696 14.1683 0.401312 13.6861 0.343323 13.1509C0.286761 12.6288 0.28747 11.977 0.28747 11.1834V9.51411C0.28747 8.84785 0.281286 8.36721 0.399176 7.95656C0.671091 7.00941 1.41109 6.26838 2.35823 5.99645C2.76888 5.87855 3.24952 5.88579 3.91579 5.88579C4.11977 5.88579 4.14542 5.88325 4.16238 5.88053C4.23526 5.8687 4.30403 5.83669 4.35839 5.78674C4.37104 5.77511 4.38755 5.7561 4.51436 5.59494L8.25648 0.839033L8.25754 0.837979L8.27861 0.811633ZM1.69116 11.1834C1.69116 12.0083 1.69211 12.5712 1.73859 13.0002C1.78365 13.4158 1.86467 13.6222 1.96937 13.7663C2.05914 13.8898 2.16727 13.999 2.29079 14.0888C2.43495 14.1935 2.6421 14.2745 3.05797 14.3195C3.45891 14.363 3.97631 14.3656 4.71564 14.3659C4.30795 13.8053 4.06447 13.1172 4.06437 12.371V8.59412H5.46807V12.371C5.46832 13.4734 6.3616 14.367 7.46401 14.367H10.0374C10.6286 14.367 11.0269 14.3663 11.3368 14.3385C11.6339 14.3118 11.7956 14.2639 11.9196 14.1984C12.024 14.1431 12.1213 14.0747 12.2094 13.996C12.3139 13.9025 12.4151 13.7679 12.5434 13.4986C12.6774 13.2177 12.8162 12.8451 13.0219 12.2909L13.9787 9.71328C14.1848 9.15822 14.253 8.96737 14.278 8.83439C14.4617 7.85698 13.8092 6.91901 12.829 6.75098C12.6956 6.72816 12.4928 6.72464 11.9006 6.72464H10.9627C10.7737 6.72464 10.5693 6.72663 10.4 6.70672C10.2211 6.68568 9.96696 6.6303 9.74764 6.43167C9.64448 6.33817 9.5595 6.22616 9.49683 6.10183C9.36384 5.8379 9.37793 5.57905 9.40515 5.40104C9.43094 5.23267 9.48666 5.03623 9.53688 4.8541L10.0079 3.14585L10.0174 3.11108C10.1488 2.61344 10.0077 2.08344 9.64648 1.71687L9.60854 1.67893L9.55058 1.6431C9.48789 1.62049 9.41419 1.6382 9.36932 1.69368L9.35773 1.70633L9.35878 1.70738L5.61666 6.46224C5.51816 6.58741 5.42231 6.71336 5.30683 6.81948C5.05069 7.05477 4.73119 7.20945 4.3879 7.26525C4.23309 7.29038 4.07507 7.28843 3.91579 7.28843C3.1535 7.28843 2.9191 7.29576 2.74604 7.34534C2.26358 7.48385 1.88558 7.86087 1.74702 8.34331C1.69732 8.51642 1.69116 8.75116 1.69116 9.51411V11.1834Z" fill="currentColor"/>
                    </svg>
                  </button>

                  {/* Thumbs Down */}
                  <button
                    className="flex items-center justify-center w-7 h-7 rounded hover:bg-gray-100 transition-colors"
                    aria-label="Dislike response"
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" className="text-gray-500">
                      <path d="M7.72451 15.1086C7.18929 15.7706 6.22975 15.8695 5.57357 15.3598L5.44643 15.2493L5.42247 15.2253L5.41934 15.2233L5.39016 15.1941C4.68239 14.4805 4.40679 13.4442 4.66589 12.4731L4.66693 12.4689L4.67631 12.4335L4.67735 12.4314L5.14318 10.7432C5.15243 10.7096 5.1613 10.6784 5.16923 10.6494C5.13878 10.6493 5.10558 10.6484 5.07023 10.6484H4.14274C3.62288 10.6484 3.27015 10.6513 2.9912 10.6035C1.25757 10.3069 0.103662 8.64709 0.42863 6.91861C0.480965 6.64044 0.606164 6.30981 0.787119 5.8223L1.73336 3.27328C1.92812 2.74859 2.08912 2.31215 2.25442 1.96542C2.42515 1.60731 2.62191 1.296 2.91304 1.03584C3.08408 0.883016 3.273 0.751185 3.47579 0.644009C3.82102 0.461569 4.18214 0.385575 4.57731 0.350131C4.95993 0.315849 5.42553 0.316783 5.98521 0.316783H11.0916C11.876 0.316783 12.52 0.316134 13.0362 0.372015C13.5655 0.429358 14.0423 0.552599 14.4608 0.856601C14.7007 1.03091 14.9117 1.24199 15.086 1.48187C15.3901 1.90033 15.5143 2.37716 15.5717 2.90645C15.6276 3.42275 15.6269 4.06727 15.6269 4.85209V6.5028C15.6269 7.16167 15.633 7.63697 15.5164 8.04306C15.2475 8.97969 14.5158 9.71248 13.5791 9.9814C13.173 10.098 12.6977 10.0908 12.0389 10.0908C11.8372 10.0908 11.8118 10.0933 11.795 10.096C11.723 10.1077 11.6549 10.1394 11.6012 10.1888C11.5887 10.2003 11.5724 10.2191 11.447 10.3784L7.74639 15.0815L7.74535 15.0826L7.72451 15.1086ZM14.2388 4.85209C14.2388 4.03635 14.2379 3.47971 14.1919 3.05547C14.1473 2.64449 14.0672 2.44037 13.9637 2.29785C13.8749 2.17569 13.768 2.06776 13.6458 1.97896C13.5033 1.87539 13.2984 1.7953 12.8872 1.75074C12.4907 1.70779 11.979 1.70518 11.2479 1.70489C11.6511 2.25924 11.8918 2.93974 11.8919 3.67762V7.41257H10.5038V3.67762C10.5036 2.58751 9.62023 1.70384 8.53007 1.70384H5.98521C5.40065 1.70384 5.00679 1.70449 4.70028 1.73198C4.40651 1.75836 4.24662 1.80577 4.12399 1.87058C4.02069 1.92518 3.92452 1.99283 3.8374 2.07067C3.73401 2.16312 3.634 2.29627 3.50705 2.56255C3.37462 2.84034 3.23734 3.2088 3.03393 3.75682L2.08768 6.30584C1.88395 6.85474 1.81646 7.04347 1.79172 7.17497C1.61005 8.14152 2.25533 9.06908 3.22464 9.23524C3.35654 9.25781 3.55717 9.26129 4.14274 9.26129H5.07023C5.25717 9.26129 5.4593 9.25932 5.62672 9.27901C5.80364 9.29982 6.05492 9.35458 6.27179 9.551C6.37381 9.64347 6.45784 9.75424 6.51982 9.87719C6.65133 10.1382 6.6374 10.3942 6.61048 10.5702C6.58498 10.7367 6.52988 10.931 6.48022 11.1111L6.01439 12.8003L6.00501 12.8347C5.87513 13.3268 6.01464 13.8509 6.37184 14.2134L6.40935 14.251L6.46667 14.2864C6.52866 14.3088 6.60155 14.2912 6.64591 14.2364L6.65738 14.2239L6.65633 14.2228L10.3569 9.52078C10.4543 9.397 10.5491 9.27245 10.6633 9.1675C10.9166 8.93483 11.2325 8.78186 11.572 8.72669C11.7251 8.70184 11.8814 8.70376 12.0389 8.70376C12.7927 8.70376 13.0245 8.69651 13.1956 8.64748C13.6727 8.51051 14.0465 8.13768 14.1836 7.6606C14.2327 7.48941 14.2388 7.25727 14.2388 6.5028V4.85209Z" fill="currentColor"/>
                    </svg>
                  </button>
                </div>
                <div style={{flex: "1 1 0%"}}></div>
              </div>
            </div>
          </div>
        </div>
      </div>
      {/* Lightbox overlay for images */}
      {lightboxUrl && (
        <div
          className="fixed inset-0 z-[9999] grid items-center justify-items-center bg-black/50 backdrop-brightness-75 overflow-y-auto md:p-10 p-4"
          onClick={() => setLightboxUrl(null)}
          data-state="open"
          style={{ pointerEvents: 'auto' }}
        >
          <div role="dialog" aria-modal="true" className="max-w-[60rem] px-3 pb-14 pt-3" onClick={(e) => e.stopPropagation()}>
            <div className="relative">
              <button
                type="button"
                aria-label="Close image preview"
                className="inline-flex items-center justify-center relative shrink-0 h-8 w-8 rounded-md active:scale-95 text-white hover:bg-white/10 absolute left-full top-0 ml-1.5"
                onClick={() => setLightboxUrl(null)}
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 256 256"><path d="M205.66,194.34a8,8,0,0,1-11.32,11.32L128,139.31,61.66,205.66a8,8,0,0,1-11.32-11.32L116.69,128,50.34,61.66A8,8,0,0,1,61.66,50.34L128,116.69l66.34-66.35a8,8,0,0,1,11.32,11.32L139.31,128Z"></path></svg>
              </button>
              <div className="rounded-md overflow-hidden shadow-[0_4px_32px_rgba(0,0,0,0.3),_0_0_0_0.5px_rgba(0,0,0,0.25)]">
                <img
                  src={lightboxUrl}
                  alt="Preview"
                  className="block w-full max-h-[calc(100vh-4rem)] object-contain"
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
