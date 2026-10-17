"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const PREFERENCE_KEY = "qk.music.enabled";
const TRACK = "/audio/outer-space-loop.mp3";

/**
 * A quiet CC0 soundtrack that starts **as soon as the screen opens**.
 *
 * Browser reality, stated because it cannot be worked around: an unmuted
 * `HTMLMediaElement.play()` is only allowed before a user gesture if the site has
 * already earned autoplay permission (the visitor has interacted before, or the browser
 * was told to allow audio). So we do both:
 *
 *  1. attempt playback immediately on mount, which succeeds for a returning visitor and
 *     on any browser that grants autoplay;
 *  2. if that attempt is rejected, start on the **first** interaction anywhere on the page
 *     (`pointerdown` / `keydown`), so the music begins as early as the browser permits.
 *
 * Playback pauses while the tab is hidden and resumes when it is shown again, and the
 * user's mute choice is remembered, so a muted visitor is never autoplayed at.
 */
export function useMusic() {
  const [enabled, setEnabled] = useState(false);
  const enabledRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const start = useCallback(() => {
    if (!enabledRef.current || document.hidden) return;
    if (audioRef.current && !audioRef.current.paused) return; // already playing
    if (!audioRef.current) {
      const audio = new Audio(TRACK);
      audio.loop = true;
      audio.volume = 0.16;
      // "auto" so the fetch begins with the attempt instead of on the first play().
      audio.preload = "auto";
      audioRef.current = audio;
    }
    // Autoplay may be denied. That is expected on a first visit, not an error: the
    // gesture listeners below retry, and toggle() will start it on demand.
    void audioRef.current.play().catch(() => {
      /* denied until a gesture; start() is called again then */
    });
  }, []);

  useEffect(() => {
    let preferred = true;
    try {
      preferred = localStorage.getItem(PREFERENCE_KEY) !== "0";
    } catch { /* storage may be unavailable */ }
    enabledRef.current = preferred;
    setEnabled(preferred);

    const visibility = () => {
      if (document.hidden) audioRef.current?.pause();
      else start();
    };
    document.addEventListener("pointerdown", start);
    document.addEventListener("keydown", start);
    document.addEventListener("visibilitychange", visibility);

    // Try to have music playing the moment the screen opens.
    start();

    return () => {
      document.removeEventListener("pointerdown", start);
      document.removeEventListener("keydown", start);
      document.removeEventListener("visibilitychange", visibility);
      audioRef.current?.pause();
      audioRef.current = null;
    };
  }, [start]);

  const toggle = useCallback(() => {
    const next = !enabledRef.current;
    enabledRef.current = next;
    setEnabled(next);
    try {
      localStorage.setItem(PREFERENCE_KEY, next ? "1" : "0");
    } catch { /* storage may be unavailable */ }
    if (next) start();
    else audioRef.current?.pause();
  }, [start]);

  return { enabled, toggle };
}
