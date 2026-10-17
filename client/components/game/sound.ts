"use client";

/**
 * Synthesised sound effects. WebAudio only; the separately licensed background
 * soundtrack is managed by music.ts. No audio is inherited from the design reference.
 *
 * Each cue is a short envelope over one or two oscillators plus a filtered
 * noise burst. They are deliberately dry and small: this is a thinking game, so
 * the audio carries state changes (your piece moved, something was measured)
 * and nothing else.
 *
 * The mute toggle is persisted to localStorage so a player who turns sound off
 * does not get it back on every reload.
 */

import { useCallback, useEffect, useRef, useState } from "react";

const MUTE_KEY = "qk.sound.muted";

export type SfxCue =
  /** An ordinary step. */
  | "move"
  /** A capture: brighter, with a second partial. */
  | "capture"
  /** A split: the shimmer of a piece becoming uncertain. */
  | "split"
  /** A collapse: the reveal resolving. */
  | "collapse"
  /** Selecting or clearing a piece. */
  | "select"
  /** Any button press. */
  | "click"
  /** The game ended in your favour. */
  | "win"
  /** The game ended against you, or in a draw. */
  | "lose";

function readMuted(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(MUTE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeMuted(muted: boolean): void {
  try {
    window.localStorage.setItem(MUTE_KEY, muted ? "1" : "0");
  } catch {
    /* storage blocked: the setting simply will not persist */
  }
}

export interface SoundControls {
  muted: boolean;
  toggle: () => void;
  play: (cue: SfxCue) => void;
}

/**
 * Build the cue graphs lazily. The context is created on the first play rather
 * than on mount, because browsers refuse to start audio before a user gesture
 * and a suspended context just logs a warning.
 */
export function useSound(): SoundControls {
  const [muted, setMuted] = useState(false);
  const contextRef = useRef<AudioContext | null>(null);
  const hydrated = useRef(false);

  useEffect(() => {
    if (hydrated.current) return;
    hydrated.current = true;
    setMuted(readMuted());
  }, []);

  const ensureContext = useCallback((): AudioContext | null => {
    if (typeof window === "undefined") return null;
    const Ctor = window.AudioContext ?? (window as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    if (!contextRef.current) {
      try {
        contextRef.current = new Ctor();
      } catch {
        return null;
      }
    }
    // Autoplay policy: a context created before a gesture starts suspended.
    if (contextRef.current.state === "suspended") void contextRef.current.resume();
    return contextRef.current;
  }, []);

  const play = useCallback(
    (cue: SfxCue) => {
      if (readMuted()) return;
      const ctx = ensureContext();
      if (!ctx) return;
      const now = ctx.currentTime;

      switch (cue) {
        case "move": {
          // A low woodblock: short, damped, no top end.
          tone(ctx, now, { type: "sine", freq: 196, endFreq: 150, gain: 0.16, attack: 0.004, decay: 0.09 });
          noise(ctx, now, { gain: 0.05, decay: 0.04, freq: 1400, q: 1.2 });
          break;
        }
        case "capture": {
          // Two partials a fifth apart reads as "metal on metal".
          tone(ctx, now, { type: "triangle", freq: 523, endFreq: 470, gain: 0.16, attack: 0.003, decay: 0.16 });
          tone(ctx, now + 0.012, { type: "triangle", freq: 784, endFreq: 700, gain: 0.1, attack: 0.003, decay: 0.14 });
          noise(ctx, now, { gain: 0.08, decay: 0.09, freq: 3200, q: 2.4 });
          break;
        }
        case "split": {
          // An upward glide: the piece stops being one place.
          tone(ctx, now, { type: "sine", freq: 320, endFreq: 880, gain: 0.1, attack: 0.01, decay: 0.26 });
          noise(ctx, now, { gain: 0.04, decay: 0.2, freq: 2600, q: 3 });
          break;
        }
        case "collapse": {
          // Downward glide plus a soft bell, so a measurement lands.
          tone(ctx, now, { type: "sine", freq: 880, endFreq: 330, gain: 0.13, attack: 0.006, decay: 0.34 });
          tone(ctx, now + 0.05, { type: "sine", freq: 1320, endFreq: 660, gain: 0.06, attack: 0.006, decay: 0.4 });
          noise(ctx, now, { gain: 0.05, decay: 0.26, freq: 4200, q: 1.6 });
          break;
        }
        case "select": {
          tone(ctx, now, { type: "sine", freq: 660, gain: 0.07, attack: 0.003, decay: 0.05 });
          break;
        }
        case "click": {
          tone(ctx, now, { type: "square", freq: 1180, endFreq: 900, gain: 0.045, attack: 0.002, decay: 0.028 });
          break;
        }
        case "win": {
          // A major triad, arpeggiated.
          [523, 659, 784, 1047].forEach((freq, i) => {
            tone(ctx, now + i * 0.075, { type: "triangle", freq, gain: 0.13, attack: 0.005, decay: 0.34 });
          });
          break;
        }
        case "lose": {
          // A falling minor figure.
          [392, 330, 262].forEach((freq, i) => {
            tone(ctx, now + i * 0.11, { type: "sine", freq, gain: 0.12, attack: 0.006, decay: 0.42 });
          });
          break;
        }
      }
    },
    [ensureContext],
  );

  const toggle = useCallback(() => {
    setMuted((current) => {
      const next = !current;
      writeMuted(next);
      return next;
    });
  }, []);

  useEffect(() => {
    return () => {
      contextRef.current?.close().catch(() => undefined);
      contextRef.current = null;
    };
  }, []);

  return { muted, toggle, play };
}

interface ToneSpec {
  type: OscillatorType;
  freq: number;
  endFreq?: number;
  gain: number;
  attack: number;
  decay: number;
}

function tone(ctx: AudioContext, at: number, spec: ToneSpec): void {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = spec.type;
  osc.frequency.setValueAtTime(spec.freq, at);
  if (spec.endFreq !== undefined) {
    osc.frequency.exponentialRampToValueAtTime(Math.max(20, spec.endFreq), at + spec.decay);
  }
  gain.gain.setValueAtTime(0.0001, at);
  gain.gain.exponentialRampToValueAtTime(spec.gain, at + spec.attack);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + spec.attack + spec.decay);
  osc.connect(gain).connect(ctx.destination);
  osc.start(at);
  osc.stop(at + spec.attack + spec.decay + 0.02);
}

interface NoiseSpec {
  gain: number;
  decay: number;
  freq: number;
  q: number;
}

function noise(ctx: AudioContext, at: number, spec: NoiseSpec): void {
  // One short buffer of white noise, band-passed. Cheap, and reused per cue.
  const frames = Math.floor(ctx.sampleRate * (spec.decay + 0.02));
  const buffer = ctx.createBuffer(1, frames, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < frames; i += 1) {
    data[i] = (Math.random() * 2 - 1) * (1 - i / frames);
  }
  const src = ctx.createBufferSource();
  src.buffer = buffer;

  const filter = ctx.createBiquadFilter();
  filter.type = "bandpass";
  filter.frequency.value = spec.freq;
  filter.Q.value = spec.q;

  const gain = ctx.createGain();
  gain.gain.setValueAtTime(spec.gain, at);
  gain.gain.exponentialRampToValueAtTime(0.0001, at + spec.decay);

  src.connect(filter).connect(gain).connect(ctx.destination);
  src.start(at);
  src.stop(at + spec.decay + 0.02);
}
