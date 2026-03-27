import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import type { UIFundamental } from "@/lib/types";
import { fmtMoney } from "@/lib/utils";

interface FundamentalTabProps {
  fundamental: UIFundamental;
}

export function FundamentalTab({ fundamental }: FundamentalTabProps) {
  const [showRaw, setShowRaw] = useState(false);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Valuation Models</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">Model Fair Value</TableHead>
                <TableHead className="text-right">Weight</TableHead>
                <TableHead className="text-right">Contribution</TableHead>
                <TableHead className="text-right">Confidence</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {fundamental.models.map((m) => {
                const contribution =
                  m.fair_value != null ? m.fair_value * m.weight : null;
                return (
                  <TableRow key={m.name}>
                    <TableCell className="font-medium">{m.name}</TableCell>
                    <TableCell className="text-right font-mono">
                      {fmtMoney(m.fair_value)}
                    </TableCell>
                    <TableCell className="text-right">
                      {(m.weight * 100).toFixed(0)}%
                    </TableCell>
                    <TableCell className="text-right font-mono text-slate-500 dark:text-slate-400">
                      {fmtMoney(contribution)}
                    </TableCell>
                    <TableCell className="text-right capitalize">
                      {m.confidence}
                    </TableCell>
                  </TableRow>
                );
              })}
              {(() => {
                const blended = fundamental.models.reduce(
                  (sum, m) =>
                    m.fair_value != null ? sum + m.fair_value * m.weight : sum,
                  0,
                );
                const hasAny = fundamental.models.some(
                  (m) => m.fair_value != null,
                );
                return hasAny ? (
                  <TableRow className="border-t-2 font-semibold">
                    <TableCell>Blended Fair Value</TableCell>
                    <TableCell />
                    <TableCell className="text-right">
                      {`${(fundamental.models.reduce((s, m) => s + m.weight, 0) * 100).toFixed(0)}%`}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {fmtMoney(blended)}
                    </TableCell>
                    <TableCell />
                  </TableRow>
                ) : null;
              })()}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {fundamental.forward_guidance && (
        <Card>
          <CardHeader>
            <CardTitle>Forward Guidance</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-1">
            {fundamental.forward_guidance.guidance_period && (
              <p>
                <span className="text-slate-500">Period:</span>{" "}
                {fundamental.forward_guidance.guidance_period}
              </p>
            )}
            {(fundamental.forward_guidance.revenue_low != null ||
              fundamental.forward_guidance.revenue_mid != null) && (
              <p>
                <span className="text-slate-500">Revenue Guidance:</span>{" "}
                {fundamental.forward_guidance.revenue_low != null &&
                fundamental.forward_guidance.revenue_high != null
                  ? `${fmtMoney(fundamental.forward_guidance.revenue_low)} – ${fmtMoney(fundamental.forward_guidance.revenue_high)}`
                  : fmtMoney(fundamental.forward_guidance.revenue_mid)}
                {fundamental.forward_guidance.revenue_mid != null &&
                  fundamental.forward_guidance.revenue_low != null &&
                  ` (mid: ${fmtMoney(fundamental.forward_guidance.revenue_mid)})`}
              </p>
            )}
            {fundamental.forward_guidance.revenue_growth_pct != null && (
              <p>
                <span className="text-slate-500">Revenue Growth:</span>{" "}
                {fundamental.forward_guidance.revenue_growth_pct.toFixed(1)}%
              </p>
            )}
            {fundamental.forward_guidance.eps_estimate != null && (
              <p>
                <span className="text-slate-500">EPS Estimate:</span>{" "}
                {fmtMoney(fundamental.forward_guidance.eps_estimate)}
              </p>
            )}
            {fundamental.forward_guidance.source && (
              <p>
                <span className="text-slate-500">Source:</span>{" "}
                {fundamental.forward_guidance.source}
              </p>
            )}
            {fundamental.forward_guidance.filing_date && (
              <p>
                <span className="text-slate-500">Filing Date:</span>{" "}
                {fundamental.forward_guidance.filing_date}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {fundamental.notes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc pl-5 text-sm text-slate-600 dark:text-slate-300 space-y-1">
              {fundamental.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {fundamental.raw_payload && (
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
                {JSON.stringify(fundamental.raw_payload, null, 2)}
              </pre>
            </CardContent>
          )}
        </Card>
      )}
    </div>
  );
}
