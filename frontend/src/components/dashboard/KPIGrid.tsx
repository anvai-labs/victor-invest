import { Card, CardContent } from "@/components/ui/card";
import type { UISummary } from "@/lib/types";
import { actionColor, fmtMoney, fmtPct, cn } from "@/lib/utils";

interface KPIGridProps {
  summary: UISummary;
}

interface KPICardProps {
  label: string;
  value: string;
  className?: string;
}

function KPICard({ label, value, className }: KPICardProps) {
  return (
    <Card>
      <CardContent className="py-3">
        <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
          {label}
        </p>
        <p className={cn("mt-1 text-xl font-semibold", className)}>{value}</p>
      </CardContent>
    </Card>
  );
}

export function KPIGrid({ summary }: KPIGridProps) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <KPICard
        label="Action"
        value={summary.action}
        className={actionColor(summary.action)}
      />
      <KPICard label="Price" value={fmtMoney(summary.price)} />
      <KPICard
        label="Fair Value"
        value={fmtMoney(summary.fair_value)}
      />
      <KPICard
        label="Target Return"
        value={fmtPct(summary.target_return_pct)}
        className={
          summary.target_return_pct != null
            ? summary.target_return_pct > 5
              ? "text-good dark:text-emerald-400"
              : summary.target_return_pct < -5
                ? "text-bad dark:text-red-400"
                : "text-warn dark:text-amber-400"
            : undefined
        }
      />
      <KPICard label="Basis" value={summary.valuation_basis} />
      <KPICard label="Quality" value={summary.data_quality} />
    </div>
  );
}
