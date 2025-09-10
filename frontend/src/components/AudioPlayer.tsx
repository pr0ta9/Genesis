import React, { useEffect, useRef, useState } from "react";

type Props = { src: string; filename?: string };

function fmt(t: number) {
  if (!Number.isFinite(t) || t < 0) return "0:00";
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function AudioPlayer({ src, filename }: Props) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [current, setCurrent] = useState(0);
  const [rate, setRate] = useState(1);
  const [menuOpen, setMenuOpen] = useState(false);
  const [speedMenuOpen, setSpeedMenuOpen] = useState(false);

  const progress = duration > 0 ? (current / duration) * 100 : 0;

  useEffect(() => {
    const audio = audioRef.current!;
    const onLoaded = () => setDuration(audio.duration || 0);
    const onTime = () => setCurrent(audio.currentTime || 0);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);

    audio.addEventListener("loadedmetadata", onLoaded);
    audio.addEventListener("timeupdate", onTime);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);

    return () => {
      audio.removeEventListener("loadedmetadata", onLoaded);
      audio.removeEventListener("timeupdate", onTime);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
    };
  }, []);

  // click-outside to close menu
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!menuOpen) return;
      if (wrapRef.current && e.target instanceof Node && wrapRef.current.contains(e.target)) return;
      setMenuOpen(false);
      setSpeedMenuOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [menuOpen]);

  const toggle = () => {
    const a = audioRef.current!;
    if (a.paused) a.play();
    else a.pause();
  };

  const onSeek = (v: number) => {
    const a = audioRef.current!;
    const clamped = Math.max(0, Math.min(v, duration || 0));
    a.currentTime = clamped;
    setCurrent(clamped);
  };

  const setPlayback = (r: number) => {
    const a = audioRef.current!;
    a.playbackRate = r;
    setRate(r);
    setSpeedMenuOpen(false);
    setMenuOpen(false);
  };

  const toggleSpeedMenu = () => {
    setSpeedMenuOpen(!speedMenuOpen);
  };

  const toggleMainMenu = () => {
    setMenuOpen(!menuOpen);
    setSpeedMenuOpen(false);
  };

  return (
    <div className="w-full">
      <div ref={wrapRef} className="relative rounded-3xl bg-gradient-to-br from-gray-50 to-gray-100 border border-gray-200/60 p-5 shadow-lg backdrop-blur-sm">
        {/* Hidden native controls; we drive it via custom UI */}
        <audio ref={audioRef} src={src} preload="metadata" />

        {/* File info */}
        {filename && (
          <div className="mb-4 text-sm font-medium text-gray-700 truncate">
            {filename}
          </div>
        )}

        {/* Main controls row */}
        <div className="flex items-center gap-4">
          {/* Play/Pause Button */}
          <button
            onClick={toggle}
            className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-gray-900 text-white hover:bg-gray-800 active:scale-95 transition-all duration-200 shadow-lg hover:shadow-xl"
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? (
              <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3 2h3v12H3V2zm7 0h3v12h-3V2z"/>
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
                <path d="M4 2.5v11l9-5.5-9-5.5z"/>
              </svg>
            )}
          </button>

          {/* Timeline and Time */}
          <div className="flex-1 flex items-center gap-3">
            <span className="text-xs tabular-nums text-gray-500 w-9 text-right">{fmt(current)}</span>
            <div className="flex-1 relative">
              <input
                type="range"
                min={0}
                max={Math.max(1, duration)}
                step={0.01}
                value={Math.min(current, duration || 0)}
                onChange={(e) => onSeek(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-full appearance-none cursor-pointer slider"
                aria-label="Seek"
              />
            </div>
            <span className="text-xs tabular-nums text-gray-500 w-9">{fmt(duration)}</span>
          </div>

          {/* Three Dots Menu Button */}
          <button
            onClick={toggleMainMenu}
            className="flex items-center justify-center w-10 h-10 rounded-full bg-white/70 hover:bg-white border border-gray-200/60 transition-all duration-200 text-gray-600 hover:text-gray-800 shadow-sm hover:shadow-md"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            aria-label="More options"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <circle cx="3" cy="8" r="1.5"/>
              <circle cx="8" cy="8" r="1.5"/>
              <circle cx="13" cy="8" r="1.5"/>
            </svg>
          </button>

          {/* Main Dropdown Menu */}
          {menuOpen && !speedMenuOpen && (
            <div
              role="menu"
              className="absolute top-full right-0 mt-2 z-20 w-48 rounded-2xl border border-gray-200/60 bg-white/95 backdrop-blur-md shadow-2xl overflow-hidden"
              style={{
                animation: 'fadeIn 0.2s ease-out'
              }}
            >
              <div className="p-2">
                <button
                  onClick={toggleSpeedMenu}
                  className="w-full text-left rounded-xl px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-all duration-200 flex items-center justify-between"
                >
                  <span>Playback Speed</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">{rate === 1 ? 'Normal' : `${rate}×`}</span>
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="text-gray-400">
                      <path d="M6 4l4 4-4 4V4z"/>
                    </svg>
                  </div>
                </button>
                
                <a
                  role="menuitem"
                  className="flex items-center gap-3 w-full px-3 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors duration-200 rounded-xl"
                  href={src}
                  download={filename || "audio-file"}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" className="text-gray-500">
                    <path d="M8.5 1.5V8H7V1.5a.5.5 0 0 1 1 0z"/>
                    <path d="M7.646 8.854a.5.5 0 0 0 .708 0l2-2a.5.5 0 0 0-.708-.708L8.5 7.293V8.5h-1V7.293l-1.146-1.147a.5.5 0 0 0-.708.708l2 2z"/>
                    <path d="M14 14H2a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1h3.5l1 1h3l1-1H14a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1z"/>
                  </svg>
                  Download
                </a>
              </div>
            </div>
          )}

          {/* Speed Selection Menu */}
          {menuOpen && speedMenuOpen && (
            <div
              role="menu"
              className="absolute top-full right-0 mt-2 z-20 w-48 rounded-2xl border border-gray-200/60 bg-white/95 backdrop-blur-md shadow-2xl overflow-hidden"
              style={{
                animation: 'slideIn 0.2s ease-out'
              }}
            >
              <div className="p-2">
                <div className="flex items-center gap-2 px-3 py-2 mb-2">
                  <button
                    onClick={() => setSpeedMenuOpen(false)}
                    className="p-1 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="text-gray-500">
                      <path d="M10 4L6 8l4 4V4z"/>
                    </svg>
                  </button>
                  <span className="text-xs uppercase tracking-wide text-gray-500 font-semibold">
                    Playback Speed
                  </span>
                </div>
                
                <div className="space-y-1">
                  {[0.5, 0.75, 1, 1.25, 1.5, 2].map((r) => (
                    <button
                      key={r}
                      role="menuitemradio"
                      aria-checked={rate === r}
                      onClick={() => setPlayback(r)}
                      className={`w-full text-left rounded-xl px-3 py-2.5 text-sm transition-all duration-200 flex items-center justify-between ${
                        rate === r 
                          ? "bg-blue-50 text-blue-700 font-semibold shadow-sm" 
                          : "hover:bg-gray-50 text-gray-700"
                      }`}
                    >
                      <span>{r === 1 ? 'Normal' : `${r}× speed`}</span>
                      {rate === r && (
                        <div className="w-1.5 h-1.5 rounded-full bg-blue-500"></div>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <style jsx>{`
        .slider {
          background: linear-gradient(to right, #1f2937 0%, #1f2937 ${progress}%, #e5e7eb ${progress}%, #e5e7eb 100%);
        }

        .slider::-webkit-slider-thumb {
          appearance: none;
          height: 18px;
          width: 18px;
          border-radius: 50%;
          background: #1f2937;
          cursor: pointer;
          border: 3px solid #ffffff;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
          transition: all 0.2s ease;
        }

        .slider::-webkit-slider-thumb:hover {
          transform: scale(1.1);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }

        .slider::-moz-range-thumb {
          height: 18px;
          width: 18px;
          border-radius: 50%;
          background: #1f2937;
          cursor: pointer;
          border: 3px solid #ffffff;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
          transition: all 0.2s ease;
        }

        .slider::-moz-range-thumb:hover {
          transform: scale(1.1);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }

        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(-8px) scale(0.95);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }

        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateX(8px) scale(0.95);
          }
          to {
            opacity: 1;
            transform: translateX(0) scale(1);
          }
        }
      `}</style>
    </div>
  );
}