import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes with conflict resolution. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const USD_COMPACT = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

const PCT = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const INT = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

export function fmtMoney(v: number | null | undefined): string {
  if (v == null) return "\u2014";
  return Math.abs(v) >= 1_000_000 ? USD_COMPACT.format(v) : USD.format(v);
}

export function fmtPct(v: number | null | undefined): string {
  if (v == null) return "\u2014";
  return PCT.format(v / 100);
}

export function fmtInt(v: number | null | undefined): string {
  if (v == null) return "\u2014";
  return INT.format(v);
}

export function actionColor(action: string): string {
  const a = action.toLowerCase();
  if (a.includes("strong buy") || a.includes("buy")) return "text-good dark:text-emerald-400";
  if (a.includes("strong sell") || a.includes("sell")) return "text-bad dark:text-red-400";
  return "text-warn dark:text-amber-400";
}

export function returnColor(pct: number | null | undefined): string {
  if (pct == null) return "text-slate-500";
  if (pct > 5) return "text-good dark:text-emerald-400";
  if (pct < -5) return "text-bad dark:text-red-400";
  return "text-warn dark:text-amber-400";
}
