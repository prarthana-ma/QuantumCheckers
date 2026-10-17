"use client";

import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";

import { cn } from "@/lib/utils";

/**
 * Single-thumb slider. Radix requires exactly as many thumbs as `value` entries, so
 * the thumb count is derived from the value rather than hardcoded.
 */
const Slider = React.forwardRef<
    React.ElementRef<typeof SliderPrimitive.Root>,
    React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>
>(({ className, value, ...props }, ref) => {
    const thumbs = Array.isArray(value) ? value.length : 1;
    return (
        <SliderPrimitive.Root
            ref={ref}
            className={cn("relative flex w-full touch-none select-none items-center", className)}
            {...props}
            value={value}
        >
            <SliderPrimitive.Track className="relative h-2 w-full grow overflow-hidden rounded-full bg-secondary">
                <SliderPrimitive.Range className="absolute h-full bg-primary" />
            </SliderPrimitive.Track>
            {Array.from({ length: thumbs }, (_, index) => (
                <SliderPrimitive.Thumb
                    key={index}
                    className="block h-5 w-5 rounded-full border-2 border-primary bg-background ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
                />
            ))}
        </SliderPrimitive.Root>
    );
});
Slider.displayName = SliderPrimitive.Root.displayName;

export { Slider };
