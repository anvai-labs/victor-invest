import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fmtMoney, fmtPct } from "@/lib/utils";
import type { PredictionsResponse } from "@/lib/types";

interface PredictionsTabProps {
  predictions: PredictionsResponse | undefined;
}

function directionCorrect(
  predictedUpside: number | null,
  priceAtPrediction: number | null,
  actualPrice: number | null,
): boolean | null {
  if (predictedUpside == null || priceAtPrediction == null || actualPrice == null) {
    return null;
  }
  const actualReturn = ((actualPrice - priceAtPrediction) / priceAtPrediction) * 100;
  // Direction correct if both positive or both negative
  return (predictedUpside >= 0 && actualReturn >= 0) || (predictedUpside < 0 && actualReturn < 0);
}

function AccuracyCell({ correct }: { correct: boolean | null }) {
  if (correct === null) return <span className="text-slate-400">&mdash;</span>;
  return correct ? (
    <span className="text-good dark:text-emerald-400 font-medium">Correct</span>
  ) : (
    <span className="text-bad dark:text-red-400 font-medium">Wrong</span>
  );
}

export function PredictionsTab({ predictions }: PredictionsTabProps) {
  const records = predictions?.predictions ?? [];
  const latestFairValues = records[0]?.model_fair_values;

  if (records.length === 0) {
    return (
      <p className="text-slate-500 py-8 text-center">
        No prediction history available.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Prediction History</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead className="text-right">Fair Value</TableHead>
                <TableHead className="text-right">Price</TableHead>
                <TableHead className="text-right">Predicted Upside</TableHead>
                <TableHead className="text-right">Actual 30d</TableHead>
                <TableHead className="text-right">Actual 90d</TableHead>
                <TableHead className="text-center">30d Direction</TableHead>
                <TableHead className="text-center">90d Direction</TableHead>
                <TableHead>Tier</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">
                    {r.analysis_date}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {fmtMoney(r.blended_fair_value)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {fmtMoney(r.current_price)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {fmtPct(r.predicted_upside_pct)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {fmtMoney(r.actual_price_30d)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {fmtMoney(r.actual_price_90d)}
                  </TableCell>
                  <TableCell className="text-center">
                    <AccuracyCell
                      correct={directionCorrect(
                        r.predicted_upside_pct,
                        r.current_price,
                        r.actual_price_30d,
                      )}
                    />
                  </TableCell>
                  <TableCell className="text-center">
                    <AccuracyCell
                      correct={directionCorrect(
                        r.predicted_upside_pct,
                        r.current_price,
                        r.actual_price_90d,
                      )}
                    />
                  </TableCell>
                  <TableCell className="text-xs">
                    {r.tier_classification ?? "\u2014"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Per-model fair values summary */}
      {latestFairValues && (
        <Card>
          <CardHeader>
            <CardTitle>Latest Per-Model Fair Values</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-4 text-sm">
              {Object.entries(latestFairValues)
                .filter(([, v]) => v != null)
                .map(([model, value]) => (
                  <div
                    key={model}
                    className="rounded-md border border-slate-200 dark:border-slate-700 px-3 py-2"
                  >
                    <span className="text-slate-500 uppercase text-xs">
                      {model.replace(/_/g, " ")}
                    </span>
                    <p className="font-mono font-medium">{fmtMoney(value)}</p>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
