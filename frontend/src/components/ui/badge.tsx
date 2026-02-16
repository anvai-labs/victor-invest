import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "bg-slate-100 dark:bg-slate-700 text-slate-800 dark:text-slate-200",
        good: "bg-emerald-100 dark:bg-emerald-900/40 text-good dark:text-emerald-400",
        bad: "bg-red-100 dark:bg-red-900/40 text-bad dark:text-red-400",
        warn: "bg-amber-100 dark:bg-amber-900/40 text-warn dark:text-amber-400",
        neutral: "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, className }))} {...props} />;
}
