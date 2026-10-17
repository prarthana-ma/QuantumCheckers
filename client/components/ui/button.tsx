import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

/**
 * Buttons. No `asChild`: this client does not take a `@radix-ui/react-slot`
 * dependency, so links get a plain anchor styled with `buttonVariants` instead.
 */
const buttonVariants = cva(
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md border border-transparent font-display text-sm font-semibold uppercase tracking-wide transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
    {
        variants: {
            variant: {
                default:
                    "bg-primary text-primary-foreground hover:bg-primary/85 shadow-[0_0_18px_-6px_hsl(var(--primary))]",
                outline:
                    "border-border bg-transparent text-foreground hover:border-primary/60 hover:bg-primary/10",
                secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
                ghost: "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
                link: "text-primary underline-offset-4 hover:underline",
            },
            size: {
                default: "h-10 px-4 py-2",
                sm: "h-8 px-3 text-xs",
                lg: "h-12 px-8 text-base",
                icon: "h-9 w-9",
            },
        },
        defaultVariants: {
            variant: "default",
            size: "default",
        },
    },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant, size, type = "button", ...props }, ref) => (
        <button ref={ref} type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
    ),
);
Button.displayName = "Button";

export { Button, buttonVariants };