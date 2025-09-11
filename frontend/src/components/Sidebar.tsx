"use client";

import React, { useState, useEffect, useRef } from "react";
import { HealthCheck } from "./HealthCheck";
import { useApp } from "@/lib/state/AppContext";
import { createConversation, deleteConversation } from "@/lib/api/conversations";
import { useRouter, usePathname } from "next/navigation";

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const { conversations, currentConversationId, dispatch } = useApp();
  const router = useRouter();
  const pathname = usePathname();
  const [showBorder, setShowBorder] = useState(!isCollapsed);
  const prevTitlesRef = useRef<Map<string, string>>(new Map());
  const [animatedTitles, setAnimatedTitles] = useState<Map<string, string>>(new Map());
  const animTimersRef = useRef<Map<string, number>>(new Map());

  // Handle border visibility immediately when collapse state changes
  useEffect(() => {
    if (isCollapsed) {
      // Hide border immediately when collapsing
      setShowBorder(false);
    } else {
      // Show border after a short delay when expanding to sync with animation
      const timer = setTimeout(() => setShowBorder(true), 50);
      return () => clearTimeout(timer);
    }
  }, [isCollapsed]);

  // Detect conversation title changes and run a hacker-style reveal animation
  useEffect(() => {
    const prevTitles = prevTitlesRef.current;
    const changedIds: string[] = [];
    for (const conv of conversations) {
      const prevTitle = prevTitles.get(conv.id);
      if (prevTitle !== undefined && prevTitle !== conv.title) {
        changedIds.push(conv.id);
      }
    }

    if (changedIds.length > 0) {
      const charset = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
      function startAnimation(id: string, toTitle: string) {
        // Clear any existing timer
        const existing = animTimersRef.current.get(id);
        if (existing) {
          clearInterval(existing);
          animTimersRef.current.delete(id);
        }

        let reveal = 0;
        const target = toTitle || "";
        const length = target.length;
        let tick = 0;

        // Faster, shorter animation (~450ms total)
        const intervalMs = 20;
        const totalDurationMs = 450;
        const ticksNeeded = Math.max(1, Math.ceil(totalDurationMs / intervalMs));
        const revealStep = Math.max(1, Math.ceil(length / ticksNeeded));

        const intervalId = window.setInterval(() => {
          tick += 1;
          const builder: string[] = new Array(length);
          for (let i = 0; i < length; i++) {
            if (i < reveal) {
              builder[i] = target[i];
            } else {
              builder[i] = charset[Math.floor(Math.random() * charset.length)];
            }
          }
          const display = builder.join("");
          setAnimatedTitles((prev) => {
            const next = new Map(prev);
            next.set(id, display);
            return next;
          });

          reveal = Math.min(length, reveal + revealStep);
          if (reveal >= length) {
            clearInterval(intervalId);
            animTimersRef.current.delete(id);
            setAnimatedTitles((prev) => {
              const next = new Map(prev);
              next.delete(id);
              return next;
            });
          }
        }, intervalMs);
        animTimersRef.current.set(id, intervalId);
      }

      changedIds.forEach((id) => {
        const newTitle = conversations.find((c) => c.id === id)?.title || "";
        startAnimation(id, newTitle);
      });
    }

    // Update previous titles snapshot
    const nextMap = new Map<string, string>();
    for (const conv of conversations) {
      nextMap.set(conv.id, conv.title);
    }
    prevTitlesRef.current = nextMap;
  }, [conversations]);

  // Cleanup any active timers on unmount
  useEffect(() => {
    return () => {
      animTimersRef.current.forEach((intervalId) => clearInterval(intervalId));
      animTimersRef.current.clear();
    };
  }, []);

  const handleNewChat = async () => {
    try {
      const newConversation = await createConversation("New Conversation");
      // Add to conversations list and ensure it's at the top
      dispatch({ type: "set_conversations", conversations: [newConversation, ...conversations] });
      // Navigate to the new conversation, let the page component handle state updates
      router.push(`/chat/${encodeURIComponent(newConversation.id)}`);
    } catch (error) {
      console.error("Failed to create new conversation:", error);
    }
  };

  const handleConversationClick = (conversationId: string) => {
    const target = `/chat/${encodeURIComponent(conversationId)}`;
    if (pathname === target) {
      return;
    }
    // Only navigate, let the page component handle state updates
    router.push(target);
  };

  const handleDeleteConversation = async (conversationId: string, event: React.MouseEvent) => {
    event.stopPropagation(); // Prevent conversation click
    
    if (!confirm("Are you sure you want to delete this conversation?")) {
      return;
    }

    try {
      await deleteConversation(conversationId);
      // Remove from conversations list
      const updatedConversations = conversations.filter(conv => conv.id !== conversationId);
      dispatch({ type: "set_conversations", conversations: updatedConversations });
      
      // If we deleted the current conversation, navigate to another one
      if (currentConversationId === conversationId) {
        if (updatedConversations.length > 0) {
          // Navigate to the first available conversation
          router.push(`/chat/${encodeURIComponent(updatedConversations[0].id)}`);
        } else {
          // No conversations left, go to home
          router.push(`/`);
        }
      }
    } catch (error) {
      console.error("Failed to delete conversation:", error);
      alert("Failed to delete conversation. Please try again.");
    }
  };

  return (
    <div className={`${isCollapsed ? 'w-12' : 'w-64'} bg-white ${showBorder ? 'border-r border-gray-200' : ''} flex flex-col transition-all duration-300 ease-in-out`}>
      {/* Toggle Button */}
      <div className="p-3">
        <button
          onClick={onToggle}
          className="w-6 h-6 flex items-center justify-center rounded-md hover:bg-gray-100 transition-colors"
        >
          <svg
            className={`w-5 h-5 text-gray-700 transform transition-transform duration-200 ${isCollapsed ? 'rotate-180' : ''}`}
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path d="M6.83496 3.99992C6.38353 4.00411 6.01421 4.0122 5.69824 4.03801C5.31232 4.06954 5.03904 4.12266 4.82227 4.20012L4.62207 4.28606C4.18264 4.50996 3.81498 4.85035 3.55859 5.26848L3.45605 5.45207C3.33013 5.69922 3.25006 6.01354 3.20801 6.52824C3.16533 7.05065 3.16504 7.71885 3.16504 8.66301V11.3271C3.16504 12.2712 3.16533 12.9394 3.20801 13.4618C3.25006 13.9766 3.33013 14.2909 3.45605 14.538L3.55859 14.7216C3.81498 15.1397 4.18266 15.4801 4.62207 15.704L4.82227 15.79C5.03904 15.8674 5.31234 15.9205 5.69824 15.9521C6.01398 15.9779 6.383 15.986 6.83398 15.9902L6.83496 3.99992ZM18.165 11.3271C18.165 12.2493 18.1653 12.9811 18.1172 13.5702C18.0745 14.0924 17.9916 14.5472 17.8125 14.9648L17.7295 15.1415C17.394 15.8 16.8834 16.3511 16.2568 16.7353L15.9814 16.8896C15.5157 17.1268 15.0069 17.2285 14.4102 17.2773C13.821 17.3254 13.0893 17.3251 12.167 17.3251H7.83301C6.91071 17.3251 6.17898 17.3254 5.58984 17.2773C5.06757 17.2346 4.61294 17.1508 4.19531 16.9716L4.01855 16.8896C3.36014 16.5541 2.80898 16.0434 2.4248 15.4169L2.27051 15.1415C2.03328 14.6758 1.93158 14.167 1.88281 13.5702C1.83468 12.9811 1.83496 12.2493 1.83496 11.3271V8.66301C1.83496 7.74072 1.83468 7.00898 1.88281 6.41985C1.93157 5.82309 2.03329 5.31432 2.27051 4.84856L2.4248 4.57317C2.80898 3.94666 3.36012 3.436 4.01855 3.10051L4.19531 3.0175C4.61285 2.83843 5.06771 2.75548 5.58984 2.71281C6.17898 2.66468 6.91071 2.66496 7.83301 2.66496H12.167C13.0893 2.66496 13.821 2.66468 14.4102 2.71281C15.0069 2.76157 15.5157 2.86329 15.9814 3.10051L16.2568 3.25481C16.8833 3.63898 17.394 4.19012 17.7295 4.84856L17.8125 5.02531C17.9916 5.44285 18.0745 5.89771 18.1172 6.41985C18.1653 7.00898 18.165 7.74072 18.165 8.66301V11.3271ZM8.16406 15.995H12.167C13.1112 15.995 13.7794 15.9947 14.3018 15.9521C14.8164 15.91 15.1308 15.8299 15.3779 15.704L15.5615 15.6015C15.9797 15.3451 16.32 14.9774 16.5439 14.538L16.6299 14.3378C16.7074 14.121 16.7605 13.8478 16.792 13.4618C16.8347 12.9394 16.835 12.2712 16.835 11.3271V8.66301C16.835 7.71885 16.8347 7.05065 16.792 6.52824C16.7605 6.14232 16.7073 5.86904 16.6299 5.65227L16.5439 5.45207C16.32 5.01264 15.9796 4.64498 15.5615 4.3886L15.3779 4.28606C15.1308 4.16013 14.8165 4.08006 14.3018 4.03801C13.7794 3.99533 13.1112 3.99504 12.167 3.99504H8.16406C8.16407 3.99667 8.16504 3.99829 8.16504 3.99992L8.16406 15.995Z"></path>
          </svg>
        </button>
      </div>

      {/* Navigation - Hidden when collapsed */}
      {!isCollapsed && (
        <div className="flex-1 py-4 flex flex-col">
          <nav className="space-y-1 px-3 flex-1 overflow-hidden">
          {/* New Chat */}
          <div className="flex items-center mb-4">
            <button
              onClick={handleNewChat}
              className="w-full flex items-center space-x-3 px-3 py-2 text-gray-700 rounded-md hover:bg-gray-100 transition-colors"
            >
              <div className="w-5 h-5 flex items-center justify-center">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
              </div>
              <span className="text-sm font-medium">New Chat</span>
            </button>
          </div>

          {/* Settings temporarily hidden */}

          {/* Conversations Section */}
          <aside className="pt-4 last:mb-5" aria-labelledby="chats-section">
            <h2 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3 px-3" id="chats-section">Chats</h2>
            <div className="space-y-1 overflow-y-auto flex-1">
              {conversations.length === 0 ? (
                <div className="px-3 py-2 text-sm text-gray-500 italic">
                  No conversations yet
                </div>
              ) : (
                conversations.map((conversation) => (
                  <a
                    key={conversation.id}
                    tabIndex={0}
                    className={`group __menu-item hoverable flex min-h-0 cursor-pointer items-center gap-2 rounded-lg p-2 text-sm transition-colors hover:bg-gray-100 ${
                      currentConversationId === conversation.id
                        ? 'data-active bg-gray-200'
                        : ''
                    }`}
                    onClick={() => handleConversationClick(conversation.id)}
                    data-active={currentConversationId === conversation.id ? "" : undefined}
                  >
                    <div className="flex min-w-0 grow items-center gap-2.5 group-data-no-contents-gap:gap-0">
                      <div className="truncate">
                        <span dir="auto">
                          {animatedTitles.get(conversation.id) ?? (conversation.title || 'Untitled Conversation')}
                        </span>
                      </div>
                    </div>
                    <div className="trailing text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        tabIndex={0}
                        className="p-1 hover:bg-gray-200 rounded"
                        onClick={(e) => handleDeleteConversation(conversation.id, e)}
                        aria-label="Delete conversation"
                        type="button"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" className="text-red-500 hover:text-red-700">
                          <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
                        </svg>
                      </button>
                    </div>
                  </a>
                ))
              )}
            </div>
          </aside>


          </nav>
          
          {/* Health Check */}
          <div className="px-3 pb-3">
            <HealthCheck />
          </div>
        </div>
      )}
    </div>
  );
}
