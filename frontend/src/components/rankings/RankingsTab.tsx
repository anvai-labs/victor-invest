import { useState } from "react";
import { Download } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { useRankings } from "@/hooks/useRankings";
import { exportRankingsCsvUrl } from "@/lib/api";
import { fmtPct, actionColor } from "@/lib/utils";
import { PortfolioPreview } from "./PortfolioPreview";
import type { RankedSymbol } from "@/lib/types";

function RankTable({
  title,
  symbols,
  variant,
}: {
  title: string;
  symbols: RankedSymbol[];
  variant: "good" | "bad";
}) {
  if (!symbols.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {title}{" "}
          <Badge variant={variant} className="ml-2">
            {symbols.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">#</TableHead>
              <TableHead>Symbol</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Sector</TableHead>
              <TableHead className="text-right">Score</TableHead>
              <TableHead className="text-right">Return</TableHead>
              <TableHead>Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {symbols.map((s) => (
              <TableRow key={s.symbol}>
                <TableCell className="text-slate-400">{s.rank}</TableCell>
                <TableCell className="font-semibold text-accent">
                  {s.symbol}
                </TableCell>
                <TableCell className="text-slate-600 dark:text-slate-300 truncate max-w-[200px]">
                  {s.company_name}
                </TableCell>
                <TableCell className="text-sm">{s.sector}</TableCell>
                <TableCell className="text-right font-mono">
                  {s.composite_score.toFixed(1)}
                </TableCell>
                <TableCell className="text-right font-mono">
                  {fmtPct(s.target_return_pct)}
                </TableCell>
                <TableCell>
                  <span className={actionColor(s.action)}>{s.action}</span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function RankingsTab() {
  const [topN, setTopN] = useState(20);
  const { data, isLoading, error } = useRankings({ top_n: topN });

  if (isLoading)
    return <p className="text-center text-slate-500 py-8">Loading rankings...</p>;
  if (error)
    return (
      <p className="text-center text-bad py-8">
        Failed to load rankings: {String(error)}
      </p>
    );
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <label className="text-sm text-slate-500">Top N:</label>
          <select
            value={topN}
            onChange={(e) => setTopN(Number(e.target.value))}
            className="rounded border border-slate-300 dark:border-slate-600 bg-transparent px-2 py-1 text-sm"
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}>50</option>
          </select>
          <span className="text-xs text-slate-400">
            {data.total_symbols} symbols ranked
          </span>
          {data.split_suspect_symbols > 0 && (
            <span className="text-xs text-slate-400">
              {data.split_suspect_symbols} valuation outliers filtered
            </span>
          )}
        </div>
        <a href={exportRankingsCsvUrl()} download>
          <Button variant="outline" size="sm">
            <Download className="h-3.5 w-3.5 mr-1" />
            CSV
          </Button>
        </a>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <RankTable title="Longs" symbols={data.longs} variant="good" />
        <RankTable title="Shorts" symbols={data.shorts} variant="bad" />
      </div>

      {data.sector_neutral.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Sector-Neutral Pairs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.sector_neutral.map((sg) => (
              <div key={sg.sector}>
                <p className="text-sm font-medium mb-1">{sg.sector}</p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    {sg.longs.map((s) => (
                      <Badge key={s.symbol} variant="good" className="mr-1 mb-1">
                        {s.symbol} ({s.composite_score.toFixed(0)})
                      </Badge>
                    ))}
                  </div>
                  <div>
                    {sg.shorts.map((s) => (
                      <Badge key={s.symbol} variant="bad" className="mr-1 mb-1">
                        {s.symbol} ({s.composite_score.toFixed(0)})
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {data.pairs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Pair Trades</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Long</TableHead>
                  <TableHead>Short</TableHead>
                  <TableHead>Sector</TableHead>
                  <TableHead className="text-right">Spread</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.pairs.map((p, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-good dark:text-emerald-400 font-semibold">
                      {p.long.symbol}
                    </TableCell>
                    <TableCell className="text-bad dark:text-red-400 font-semibold">
                      {p.short.symbol}
                    </TableCell>
                    <TableCell>{p.sector}</TableCell>
                    <TableCell className="text-right font-mono">
                      {p.spread.toFixed(1)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <PortfolioPreview rankings={data} />
    </div>
  );
}
