"use client";

/**
 * Animated grid backdrop: a 2D canvas of drifting squares with a radial fade.
 *
 * Decorative only, `aria-hidden`, and it respects `prefers-reduced-motion` by drawing
 * a single static frame. No WebGL — the client ships no shader/GL dependency.
 */

import React, { useEffect, useRef } from "react";

export interface SquaresProps {
    direction?: "diagonal" | "up" | "right" | "down" | "left";
    /** Grid squares per second. Clamped to a minimum so the animation still reads. */
    speed?: number;
    borderColor?: string;
    squareSize?: number;
    hoverFillColor?: string;
    /** Colour the radial fade fades to. Matches the page ground. */
    fadeColor?: string;
}

const Squares: React.FC<SquaresProps> = ({
    direction = "diagonal",
    speed = 12,
    borderColor = "rgba(56, 189, 248, 0.08)",
    squareSize = 48,
    hoverFillColor = "rgba(56, 189, 248, 0.04)",
    fadeColor = "#07090d",
}) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const requestRef = useRef<number | null>(null);
    const hoveredSquareRef = useRef<{ x: number; y: number } | null>(null);
    const offsetRef = useRef({ x: 0, y: 0 });

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        let numSquaresX = 0;
        let numSquaresY = 0;

        const resizeCanvas = () => {
            // Scale for device pixel ratio so the 1px grid lines stay crisp.
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = Math.max(1, Math.floor(canvas.offsetWidth * dpr));
            canvas.height = Math.max(1, Math.floor(canvas.offsetHeight * dpr));
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            numSquaresX = Math.ceil(canvas.offsetWidth / squareSize) + 1;
            numSquaresY = Math.ceil(canvas.offsetHeight / squareSize) + 1;
        };

        const drawGrid = () => {
            const width = canvas.offsetWidth;
            const height = canvas.offsetHeight;
            ctx.clearRect(0, 0, width, height);

            const startX = Math.floor(offsetRef.current.x / squareSize) * squareSize;
            const startY = Math.floor(offsetRef.current.y / squareSize) * squareSize;

            for (let x = startX; x < width + squareSize; x += squareSize) {
                for (let y = startY; y < height + squareSize; y += squareSize) {
                    const squareX = x - (offsetRef.current.x % squareSize);
                    const squareY = y - (offsetRef.current.y % squareSize);

                    const col = Math.floor((x - startX) / squareSize);
                    const row = Math.floor((y - startY) / squareSize);
                    if (hoveredSquareRef.current?.x === col && hoveredSquareRef.current?.y === row) {
                        ctx.fillStyle = hoverFillColor;
                        ctx.fillRect(squareX, squareY, squareSize, squareSize);
                    }

                    ctx.strokeStyle = borderColor;
                    ctx.strokeRect(squareX, squareY, squareSize, squareSize);
                }
            }

            const gradient = ctx.createRadialGradient(
                width / 2,
                height / 2,
                0,
                width / 2,
                height / 2,
                Math.sqrt(width ** 2 + height ** 2) / 2,
            );
            gradient.addColorStop(0, "rgba(0, 0, 0, 0)");
            gradient.addColorStop(1, fadeColor);
            ctx.fillStyle = gradient;
            ctx.fillRect(0, 0, width, height);
        };

        const step = () => {
            const effectiveSpeed = Math.max(speed, 1);
            switch (direction) {
                case "right":
                    offsetRef.current.x = (offsetRef.current.x - effectiveSpeed + squareSize) % squareSize;
                    break;
                case "left":
                    offsetRef.current.x = (offsetRef.current.x + effectiveSpeed + squareSize) % squareSize;
                    break;
                case "up":
                    offsetRef.current.y = (offsetRef.current.y + effectiveSpeed + squareSize) % squareSize;
                    break;
                case "down":
                    offsetRef.current.y = (offsetRef.current.y - effectiveSpeed + squareSize) % squareSize;
                    break;
                case "diagonal":
                default:
                    offsetRef.current.x = (offsetRef.current.x - effectiveSpeed + squareSize) % squareSize;
                    offsetRef.current.y = (offsetRef.current.y + effectiveSpeed + squareSize) % squareSize;
                    break;
            }
        };

        const animate = () => {
            step();
            drawGrid();
            requestRef.current = requestAnimationFrame(animate);
        };

        const handleMouseMove = (event: MouseEvent) => {
            const rect = canvas.getBoundingClientRect();
            const startX = Math.floor(offsetRef.current.x / squareSize) * squareSize;
            const startY = Math.floor(offsetRef.current.y / squareSize) * squareSize;
            hoveredSquareRef.current = {
                x: Math.floor((event.clientX - rect.left + offsetRef.current.x - startX) / squareSize),
                y: Math.floor((event.clientY - rect.top + offsetRef.current.y - startY) / squareSize),
            };
        };

        const handleMouseLeave = () => {
            hoveredSquareRef.current = null;
        };

        window.addEventListener("resize", resizeCanvas);
        canvas.addEventListener("mousemove", handleMouseMove);
        canvas.addEventListener("mouseleave", handleMouseLeave);
        resizeCanvas();

        const reducedMotion =
            typeof window.matchMedia === "function" &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches;

        if (reducedMotion) {
            drawGrid();
        } else {
            requestRef.current = requestAnimationFrame(animate);
        }

        return () => {
            window.removeEventListener("resize", resizeCanvas);
            canvas.removeEventListener("mousemove", handleMouseMove);
            canvas.removeEventListener("mouseleave", handleMouseLeave);
            if (requestRef.current !== null) cancelAnimationFrame(requestRef.current);
            requestRef.current = null;
        };
    }, [direction, speed, borderColor, hoverFillColor, squareSize, fadeColor]);

    return (
        <canvas
            ref={canvasRef}
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 h-full w-full"
        />
    );
};

export default React.memo(Squares);