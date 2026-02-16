import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import type { UITechnical } from "@/lib/types";
import { fmtMoney } from "@/lib/utils";

interface TechnicalTabProps {
  technical: UITechnical;
}

export function TechnicalTab({ technical }: TechnicalTabProps) {
  const [showRaw, setShowRaw] = useState(false);
  const { moving_averages: ma, support_resistance: sr } = technical;

  const trendVariant =
    technical.trend.toLowerCase() === "bullish"
      ? "good"
      : technical.trend.toLowerCase() === "bearish"
        ? "bad"
        : "neutral";

  const metrics = [
    { label: "SMA 20", value: ma.sma_20 },
    { label: "SMA 50", value: ma.sma_50 },
    { label: "SMA 200", value: ma.sma_200 },
    { label: "EMA 12", value: ma.ema_12 },
    { label: "EMA 26", value: ma.ema_26 },
    { label: "Support", value: sr.support },
    { label: "Resistance", value: sr.resistance },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Badge variant={trendVariant}>Trend: {technical.trend}</Badge>
        {technical.rsi != null && (
          <Badge
            variant={
              technical.rsi > 70 ? "bad" : technical.rsi < 30 ? "good" : "neutral"
            }
          >
            RSI: {technical.rsi.toFixed(1)}
          </Badge>
        )}
        <Badge
          variant={
            technical.macd_signal === "bullish"
              ? "good"
              : technical.macd_signal === "bearish"
                ? "bad"
                : "neutral"
          }
        >
          MACD: {technical.macd_signal}
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Technical Metrics</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Indicator</TableHead>
                <TableHead className="text-right">Value</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {metrics.map((m) => (
                <TableRow key={m.label}>
                  <TableCell>{m.label}</TableCell>
                  <TableCell className="text-right font-mono">
                    {fmtMoney(m.value)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {technical.raw_payload && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Raw Payload</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowRaw((s) => !s)}
            >
              {showRaw ? "Hide" : "Show"}
            </Button>
          </CardHeader>
          {showRaw && (
            <CardContent>
              <pre className="max-h-96 overflow-auto rounded bg-slate-50 dark:bg-slate-900 p-3 text-xs">
                {JSON.stringify(technical.raw_payload, null, 2)}
              </pre>
            </CardContent>
          )}
        </Card>
      )}
    </div>
  );
}
