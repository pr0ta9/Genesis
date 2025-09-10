"use client";

import React, { useState } from "react";

interface ReasoningProps {
  reasoning: {
    content: string | any[];
    thinking_time?: number;
    is_expanded?: boolean;
    is_thinking?: boolean; // true when still thinking, false when complete
    additional_kwargs?: {
      reasoning_content?: string | any[];
      node_breakdown?: any[];
      workflow_reasoning?: boolean;
    };
  };
}

export function Reasoning({ reasoning }: ReasoningProps) {
  const [isExpanded, setIsExpanded] = useState(reasoning.is_expanded || false);
  const thinkingTime = reasoning.thinking_time || 5;
  const thinkingSeconds = Number(thinkingTime);
  const thinkingSecondsText = Number.isFinite(thinkingSeconds)
    ? (Math.round(thinkingSeconds * 10) / 10).toFixed(1)
    : "0.0";
  const isThinking = reasoning.is_thinking || false;
  
  // Use reasoning_content from additional_kwargs if available, otherwise fall back to content
  const reasoningContentRaw = reasoning.additional_kwargs?.reasoning_content ?? reasoning.content;
  const reasoningContent = Array.isArray(reasoningContentRaw)
    ? reasoningContentRaw
        .map((entry) => {
          if (typeof entry === "string") return entry;
          if (entry && typeof entry === "object") {
            // Prefer the 'content' field if present, otherwise stringify a compact summary
            if (typeof entry.content === "string") return entry.content;
            try {
              return JSON.stringify(entry);
            } catch {
              return String(entry);
            }
          }
          return String(entry ?? "");
        })
        .filter(Boolean)
        .join("\n\n")
    : String(reasoningContentRaw ?? "");

  // If workflow_reasoning flag is set, the per-stage UI is rendered by MessageBubble; hide legacy block
  const useWorkflow = !!reasoning.additional_kwargs?.workflow_reasoning;

  if (useWorkflow) {
    return null;
  }

  return (
    <div className="mb-4">
      {/* Thought Header */}
      <div className="mb-2">
        <div 
          className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 rounded-lg p-2 transition-colors"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600 font-medium">
              {isThinking ? `Thinking...` : `Thought for ${thinkingSecondsText} seconds`}
            </span>
            <div className="w-3.5 h-3.5 flex items-center justify-center">
              <svg 
                width="14" 
                height="14" 
                viewBox="0 0 14 14" 
                fill="none" 
                xmlns="http://www.w3.org/2000/svg"
                className={`transform transition-transform duration-200 text-gray-400 ${isExpanded ? 'rotate-180' : ''}`}
              >
                <path 
                  d="M11.8487 5.50006L11.4239 5.92389L8.6973 8.65143C8.4416 8.90712 8.21565 9.13388 8.01175 9.29791C7.79915 9.46889 7.55598 9.61762 7.25003 9.66608C7.08438 9.69228 6.91568 9.69228 6.75003 9.66608C6.44408 9.61762 6.20091 9.46889 5.98831 9.29791C5.78442 9.13388 5.55846 8.90712 5.30276 8.65143L2.5762 5.92389L2.1514 5.50006L3.00003 4.65143L3.42386 5.07623L6.1514 7.8028C6.42598 8.07738 6.59879 8.24855 6.74026 8.36237C6.87294 8.46911 6.92275 8.47819 6.93753 8.48053C6.97898 8.48709 7.02108 8.48709 7.06253 8.48053C7.07731 8.47819 7.12712 8.46911 7.2598 8.36237C7.40127 8.24855 7.57408 8.07738 7.84866 7.8028L10.5762 5.07623L11 4.65143L11.8487 5.50006Z" 
                  fill="currentColor"
                />
              </svg>
            </div>
          </div>
        </div>
      </div>

      {/* Reasoning Content */}
      {isExpanded && (
        <div className="border-l-2 border-gray-200 pl-4 ml-2 mb-4">
          <div className="flex items-start gap-3">
            <div className="w-4 h-4 flex items-center justify-center mt-0.5">
              {isThinking ? (
                // Loading/Spinning Icon for thinking state
                <svg 
                  width="16" 
                  height="16" 
                  viewBox="0 0 16 16" 
                  fill="none" 
                  xmlns="http://www.w3.org/2000/svg"
                  className="text-black animate-spin"
                >
                  <path 
                    d="M7.706 0.290 C 7.484 0.362,7.356 0.490,7.294 0.699 C 7.259 0.816,7.253 1.088,7.253 2.508 C 7.253 4.389,7.251 4.365,7.443 4.557 C 7.700 4.813,8.300 4.813,8.557 4.557 C 8.749 4.365,8.747 4.389,8.747 2.508 C 8.747 0.688,8.744 0.656,8.596 0.480 C 8.472 0.333,8.339 0.284,8.040 0.276 C 7.893 0.272,7.743 0.278,7.706 0.290 M2.753 2.266 C 2.595 2.338,2.362 2.566,2.281 2.728 C 2.197 2.897,2.193 3.085,2.269 3.253 C 2.343 3.418,4.667 5.750,4.850 5.843 C 5.109 5.976,5.375 5.911,5.643 5.649 C 5.907 5.391,5.977 5.111,5.843 4.850 C 5.750 4.667,3.418 2.343,3.253 2.269 C 3.101 2.200,2.901 2.199,2.753 2.266 M12.853 2.282 C 12.730 2.339,12.520 2.536,11.518 3.541 C 10.597 4.464,10.316 4.762,10.271 4.860 C 10.195 5.025,10.196 5.216,10.272 5.378 C 10.342 5.528,10.572 5.764,10.727 5.845 C 10.884 5.927,11.117 5.926,11.280 5.843 C 11.447 5.757,13.757 3.447,13.843 3.280 C 13.926 3.118,13.927 2.884,13.846 2.729 C 13.764 2.572,13.552 2.364,13.392 2.283 C 13.213 2.192,13.048 2.192,12.853 2.282 M0.699 7.292 C 0.404 7.385,0.258 7.620,0.258 7.999 C 0.259 8.386,0.403 8.618,0.698 8.706 C 0.816 8.741,1.079 8.747,2.508 8.747 C 3.997 8.747,4.196 8.742,4.318 8.702 C 4.498 8.644,4.644 8.498,4.702 8.318 C 4.788 8.053,4.745 7.677,4.608 7.491 C 4.578 7.451,4.492 7.384,4.417 7.343 L 4.280 7.267 2.547 7.261 C 1.152 7.257,0.791 7.263,0.699 7.292 M11.745 7.278 C 11.622 7.308,11.452 7.411,11.392 7.492 C 11.255 7.677,11.212 8.053,11.298 8.318 C 11.356 8.498,11.502 8.644,11.682 8.702 C 11.804 8.742,12.003 8.747,13.492 8.747 C 14.921 8.747,15.184 8.741,15.302 8.706 C 15.597 8.618,15.741 8.386,15.742 7.999 C 15.742 7.614,15.595 7.383,15.290 7.291 C 15.187 7.260,14.864 7.254,13.496 7.256 C 12.578 7.258,11.790 7.268,11.745 7.278 M4.853 10.282 C 4.730 10.339,4.520 10.536,3.518 11.541 C 2.597 12.464,2.316 12.762,2.271 12.860 C 2.195 13.025,2.196 13.216,2.272 13.378 C 2.342 13.528,2.572 13.764,2.727 13.845 C 2.884 13.927,3.117 13.926,3.280 13.843 C 3.447 13.757,5.757 11.447,5.843 11.280 C 5.926 11.118,5.927 10.884,5.846 10.729 C 5.764 10.572,5.552 10.364,5.392 10.283 C 5.213 10.192,5.048 10.192,4.853 10.282 M10.753 10.266 C 10.595 10.338,10.362 10.566,10.281 10.728 C 10.197 10.897,10.193 11.085,10.269 11.253 C 10.343 11.418,12.667 13.750,12.850 13.843 C 13.109 13.976,13.375 13.911,13.643 13.649 C 13.907 13.391,13.977 13.111,13.843 12.850 C 13.750 12.667,11.418 10.343,11.253 10.269 C 11.101 10.200,10.901 10.199,10.753 10.266 M7.745 11.277 C 7.620 11.309,7.451 11.412,7.392 11.492 C 7.254 11.678,7.253 11.691,7.253 13.489 C 7.253 14.921,7.259 15.184,7.294 15.302 C 7.382 15.597,7.615 15.741,8.000 15.741 C 8.385 15.741,8.618 15.597,8.706 15.302 C 8.768 15.090,8.767 11.875,8.704 11.690 C 8.644 11.514,8.575 11.430,8.420 11.346 C 8.310 11.286,8.246 11.271,8.057 11.264 C 7.930 11.259,7.790 11.265,7.745 11.277" 
                    stroke="none" 
                    fillRule="evenodd" 
                    fill="currentColor"
                  />
                </svg>
              ) : (
                // Light Bulb Icon for completed state
                <svg 
                  width="16" 
                  height="16" 
                  viewBox="0 0 24 24" 
                  fill="none" 
                  xmlns="http://www.w3.org/2000/svg"
                  className="text-yellow-500"
                >
                  <path 
                    d="M15,19H9c-0.6,0-1-0.4-1-1v-0.5c0-1.4-0.6-2.8-1.7-3.9C4.7,12,3.9,9.9,4,7.7C4.2,3.5,7.7,0.1,11.9,0L12,0c4.4,0,8,3.6,8,8c0,2.1-0.8,4.2-2.4,5.7c-1.1,1-1.6,2.4-1.6,3.8V18C16,18.6,15.6,19,15,19z M10,17h4c0.1-1.8,0.9-3.4,2.2-4.8C17.4,11.1,18,9.6,18,8c0-3.3-2.7-6-6-6l-0.1,0C8.8,2.1,6.1,4.6,6,7.8C5.9,9.4,6.6,11,7.7,12.2C9.1,13.6,9.9,15.3,10,17z" 
                    fill="currentColor"
                  />
                  <path 
                    d="M12,24L12,24c-2.2,0-4-1.8-4-4v-2c0-0.6,0.4-1,1-1h6c0.6,0,1,0.4,1,1v2C16,22.2,14.2,24,12,24z M10,19v1c0,1.1,0.9,2,2,2H12c1.1,0,2-0.9,2-2v-1H10z" 
                    fill="currentColor"
                  />
                  <path 
                    d="M9,9C8.4,9,8,8.6,8,8c0-2.2,1.8-4,4-4c0.6,0,1,0.4,1,1s-0.4,1-1,1c-1.1,0-2,0.9-2,2C10,8.6,9.6,9,9,9z" 
                    fill="currentColor"
                  />
                </svg>
              )}
            </div>
            <div className="flex-1 prose prose-sm max-w-none">
              <div className="text-gray-700 leading-relaxed whitespace-pre-wrap select-text">
                {reasoningContent}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
