"use client";

import React, { useEffect, useState } from "react";
import { buildUrl } from "@/lib/api/config";

interface HealthStatus {
  status: "checking" | "connected" | "error";
  message: string;
}

export function HealthCheck() {
  const [health, setHealth] = useState<HealthStatus>({ 
    status: "checking", 
    message: "Checking backend connection..." 
  });

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const url = buildUrl("/");
        // if (process.env.NODE_ENV !== "production") {
        //   // eslint-disable-next-line no-console
        //   console.log("[HEALTH] →", { url });
        // }
        const response = await fetch(url, {
          method: "GET",
          headers: { "Content-Type": "application/json" }
        });
        
        if (response.ok) {
          setHealth({ 
            status: "connected", 
            message: "Backend connected successfully!" 
          });
          // if (process.env.NODE_ENV !== "production") {
          //   // eslint-disable-next-line no-console
          //   console.log("[HEALTH] ← ok", { status: response.status, url });
          // }
        } else {
          setHealth({ 
            status: "error", 
            message: `Backend returned ${response.status}: ${response.statusText}` 
          });
          if (process.env.NODE_ENV !== "production") {
            // eslint-disable-next-line no-console
            console.error("[HEALTH] ← error", { status: response.status, url });
          }
        }
      } catch (error) {
        setHealth({ 
          status: "error", 
          message: `Failed to connect: ${error instanceof Error ? error.message : 'Unknown error'}` 
        });
        if (process.env.NODE_ENV !== "production") {
          // eslint-disable-next-line no-console
          console.error("[HEALTH] network error", error);
        }
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000); // Check every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = () => {
    switch (health.status) {
      case "connected": return "text-green-600 bg-green-50 border-green-200";
      case "error": return "text-red-600 bg-red-50 border-red-200";
      default: return "text-yellow-600 bg-yellow-50 border-yellow-200";
    }
  };

  const getStatusIcon = () => {
    switch (health.status) {
      case "connected":
        return (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        );
      case "error":
        return (
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
        );
      default:
        return (
          <svg className="w-5 h-5 animate-spin" fill="currentColor" viewBox="0 0 20 20">
            <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>
          </svg>
        );
    }
  };

  return (
    <div className={`p-3 rounded-lg border text-sm flex items-center space-x-2 ${getStatusColor()}`}>
      {getStatusIcon()}
      <span>{health.message}</span>
      {health.status === "error" && (
        <div className="ml-auto text-xs">
          <a 
            href="http://localhost:8000" 
            target="_blank" 
            rel="noopener noreferrer" 
            className="underline hover:no-underline"
          >
            Check Backend
          </a>
        </div>
      )}
    </div>
  );
}
