import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { RankingsResponse, PortfolioLeg } from "@/lib/types";

interface PortfolioPreviewProps {
  rankings: RankingsResponse;
}

export function PortfolioPreview({ rankings }: PortfolioPreviewProps) {
  // Build a simple equal-weight portfolio from top 5 longs + top 5 shorts
  const longLegs: PortfolioLeg[] = rankings.longs.slice(0, 5).map((s) => ({
    symbol: s.symbol,
    side: "long",
    weight: 0.1,
    sector: s.sector,
    score: s.composite_score,
  }));

  const shortLegs: PortfolioLeg[] = rankings.shorts.slice(0, 5).map((s) => ({
    symbol: s.symbol,
    side: "short",
    weight: 0.1,
    sector: s.sector,
    score: s.composite_score,
  }));

  const legs = [...longLegs, ...shortLegs];
  if (!legs.length) return null;

  const longExposure = longLegs.reduce((a, l) => a + l.weight, 0);
  const shortExposure = shortLegs.reduce((a, l) => a + l.weight, 0);
  const netExposure = longExposure - shortExposure;

  const sectorCounts = new Map<string, { long: number; short: number }>();
  for (const leg of legs) {
    const entry = sectorCounts.get(leg.sector) ?? { long: 0, short: 0 };
    entry[leg.side] += 1;
    sectorCounts.set(leg.sector, entry);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Portfolio Preview (Equal Weight)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-4 text-center text-sm">
          <div>
            <p className="text-slate-500">Long</p>
            <p className="text-lg font-semibold text-good dark:text-emerald-400">
              {(longExposure * 100).toFixed(0)}%
            </p>
          </div>
          <div>
            <p className="text-slate-500">Short</p>
            <p className="text-lg font-semibold text-bad dark:text-red-400">
              {(shortExposure * 100).toFixed(0)}%
            </p>
          </div>
          <div>
            <p className="text-slate-500">Net</p>
            <p className="text-lg font-semibold">
              {(netExposure * 100).toFixed(0)}%
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {legs.map((l) => (
            <Badge key={l.symbol} variant={l.side === "long" ? "good" : "bad"}>
              {l.symbol} {(l.weight * 100).toFixed(0)}%
            </Badge>
          ))}
        </div>

        <div>
          <p className="text-xs font-medium text-slate-500 mb-1">Sector Balance</p>
          <div className="flex flex-wrap gap-2 text-xs">
            {Array.from(sectorCounts.entries()).map(([sector, counts]) => (
              <span key={sector} className="text-slate-600 dark:text-slate-300">
                {sector}:{" "}
                <span className="text-good dark:text-emerald-400">{counts.long}L</span>/
                <span className="text-bad dark:text-red-400">{counts.short}S</span>
              </span>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
