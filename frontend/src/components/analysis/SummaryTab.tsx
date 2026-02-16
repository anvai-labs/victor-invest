import { RadialBarChart, RadialBar, PolarAngleAxis } from "recharts";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { KPIGrid } from "@/components/dashboard/KPIGrid";
import { SignalBoard } from "@/components/dashboard/SignalBoard";
import type { UIView } from "@/lib/types";
import { fmtMoney } from "@/lib/utils";

interface SummaryTabProps {
  view: UIView;
}

function ScoreGauge({ score }: { score: number }) {
  const color =
    score >= 70 ? "#1b7f46" : score >= 40 ? "#9a6700" : "#b42318";
  const data = [{ value: score, fill: color }];

  return (
    <div className="flex flex-col items-center">
      <RadialBarChart
        width={160}
        height={160}
        cx={80}
        cy={80}
        innerRadius={55}
        outerRadius={75}
        barSize={12}
        data={data}
        startAngle={180}
        endAngle={0}
      >
        <PolarAngleAxis
          type="number"
          domain={[0, 100]}
          angleAxisId={0}
          tick={false}
        />
        <RadialBar
          dataKey="value"
          cornerRadius={6}
          background={{ fill: "#e2e8f0" }}
        />
      </RadialBarChart>
      <span className="text-2xl font-bold -mt-10" style={{ color }}>
        {score}
      </span>
      <span className="text-xs text-slate-500 mt-1">Composite Score</span>
    </div>
  );
}

export function SummaryTab({ view }: SummaryTabProps) {
  const { summary, signals, fundamental } = view;

  const fairValueModels = fundamental?.models?.filter((m) => m.fair_value != null) ?? [];

  return (
    <div className="space-y-6">
      <KPIGrid summary={summary} />

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-1 flex items-center justify-center py-4">
          <ScoreGauge score={summary.composite_score} />
        </Card>

        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Investment Thesis</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p>{summary.thesis}</p>
            {summary.key_catalysts.length > 0 && (
              <div>
                <p className="font-medium text-good dark:text-emerald-400">Catalysts</p>
                <ul className="list-disc pl-5 text-slate-600 dark:text-slate-300">
                  {summary.key_catalysts.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
            )}
            {summary.key_risks.length > 0 && (
              <div>
                <p className="font-medium text-bad dark:text-red-400">Risks</p>
                <ul className="list-disc pl-5 text-slate-600 dark:text-slate-300">
                  {summary.key_risks.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {signals.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Signals</CardTitle>
          </CardHeader>
          <CardContent>
            <SignalBoard signals={signals} />
          </CardContent>
        </Card>
      )}

      {fairValueModels.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Fair Value Range</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700 text-left text-slate-500">
                    <th className="pb-2 font-medium">Model</th>
                    <th className="pb-2 font-medium text-right">Fair Value</th>
                    <th className="pb-2 font-medium text-right">Weight</th>
                    <th className="pb-2 font-medium text-right">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {fairValueModels.map((m) => (
                    <tr
                      key={m.name}
                      className="border-b border-slate-100 dark:border-slate-700/50"
                    >
                      <td className="py-1.5">{m.name}</td>
                      <td className="py-1.5 text-right font-mono">
                        {fmtMoney(m.fair_value)}
                      </td>
                      <td className="py-1.5 text-right">
                        {(m.weight * 100).toFixed(0)}%
                      </td>
                      <td className="py-1.5 text-right capitalize">
                        {m.confidence}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
