import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
    "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-mono text-xs font-medium transition-colors",
    {
        variants: {
            variant: {
                default: "border-primary/40 bg-primary/15 text-primary",
                secondary: "border-border bg-secondary text-secondary-foreground",
                destructive: "border-destructive/40 bg-destructive/15 text-destructive",
                outline: "border-border text-muted-foreground",
                seat0: "border-seat-0/40 bg-seat-0/15 text-seat-0",
                seat1: "border-seat-1/40 bg-seat-1/15 text-seat-1",
            },
        },
        defaultVariants: {
            variant: "default",
        },
    },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
    return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };