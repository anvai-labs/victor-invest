import { useEffect, useState } from "react";

interface SectorMetricData {
  fiscal_year: number;
  pe?: number;
  ps?: number;
  pb?: number;
}

interface TrendData {
  sector: string;
  current_pe: number;
  avg_pe_3yr: number;
  pe_change_pct: number;
  current_ps: number;
  avg_ps_3yr: number;
  ps_change_pct: number;
  current_pb: number;
  avg_pb_3yr: number;
  pb_change_pct: number;
  trend: "improving" | "declining" | "stable";
  volatility: number;
}

export function SectorTrends() {
  const [availableSectors, setAvailableSectors] = useState<string[]>([]);
  const [trendData, setTrendData] = useState<TrendData[]>([]);
  const [selectedSector, setSelectedSector] = useState<string>("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/ui/api/sectors/multiples")
      .then((res) => res.json())
      .then((data) => {
        if (data.sectors) {
          setAvailableSectors(data.sectors);
        }
      })
      .catch(() => setError("Failed to load sectors"));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);

    Promise.all(
      availableSectors.map((sector) =>
        fetch(`/ui/api/sectors/history?sector=${encodeURIComponent(sector)}&start_year=2019&end_year=2024`)
          .then((res) => res.json())
          .then((data) => ({ sector, data }))
      )
    )
      .then((results) => {
        const trends = results
          .filter(({ data }) => data.data && data.data.length > 0)
          .map(({ sector, data }) => calculateTrendMetrics(sector, data.data))
          .filter((trend): trend is TrendData => trend !== null)

        setTrendData(trends);
        setLoading(false);
      })
      .catch(() => {
        setError("Failed to load trend data");
        setLoading(false);
      });
  }, [availableSectors]);

  const calculateTrendMetrics = (sector: string, data: SectorMetricData[]): TrendData | null => {
    const sortedData = [...data].sort((a, b) => b.fiscal_year - a.fiscal_year);
    const latest = sortedData[0];
    const last3years = sortedData.slice(0, 3);

    if (!latest || !latest.pe) return null;

    const avgPe = last3years.reduce((sum, d) => sum + (d.pe || 0), 0) / last3years.filter((d) => d.pe).length;
    const avgPs = last3years.reduce((sum, d) => sum + (d.ps || 0), 0) / last3years.filter((d) => d.ps).length;
    const avgPb = last3years.reduce((sum, d) => sum + (d.pb || 0), 0) / last3years.filter((d) => d.pb).length;

    const peChange = avgPe > 0 ? ((latest.pe - avgPe) / avgPe) * 100 : 0;
    const psChange = avgPs > 0 && latest.ps ? ((latest.ps - avgPs) / avgPs) * 100 : 0;
    const pbChange = avgPb > 0 && latest.pb ? ((latest.pb - avgPb) / avgPb) * 100 : 0;

    const peValues: number[] = sortedData
      .filter((d): d is typeof d & { pe: number } => d.pe !== undefined)
      .map((d) => d.pe);
    if (peValues.length === 0) return null;

    const peMean = peValues.reduce((sum, v) => sum + v, 0) / peValues.length;
    const volatility = Math.sqrt(peValues.reduce((sum, v) => sum + Math.pow(v - peMean, 2), 0) / peValues.length);
    const volatilityPct = peMean > 0 ? (volatility / peMean) * 100 : 0;

    let trend: TrendData["trend"];
    if (peChange > 5) {
      trend = "improving";
    } else if (peChange < -5) {
      trend = "declining";
    } else {
      trend = "stable";
    }

    return {
      sector,
      current_pe: latest.pe,
      avg_pe_3yr: avgPe,
      pe_change_pct: peChange,
      current_ps: latest.ps || 0,
      avg_ps_3yr: avgPs,
      ps_change_pct: psChange,
      current_pb: latest.pb || 0,
      avg_pb_3yr: avgPb,
      pb_change_pct: pbChange,
      trend,
      volatility: volatilityPct,
    };
  };

  const getTrendBadge = (trend: TrendData["trend"]) => {
    const styles = {
      improving: "bg-green-100 text-green-800",
      declining: "bg-red-100 text-red-800",
      stable: "bg-gray-100 text-gray-800",
    };
    return (
      <span className={`px-2 py-1 rounded-full text-xs font-medium ${styles[trend]}`}>
        {trend.charAt(0).toUpperCase() + trend.slice(1)}
      </span>
    );
  };

  const getChangeColor = (value: number) => {
    if (value > 5) return "text-green-600";
    if (value < -5) return "text-red-600";
    return "text-gray-600";
  };

  const filteredData = selectedSector === "all"
    ? trendData
    : trendData.filter((t) => t.sector === selectedSector);

  if (error) {
    return (
      <div className="bg-destructive/10 text-destructive p-4 rounded-md">
        {error}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        Loading trend analysis...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <div>
          <label className="text-sm font-medium mb-2 block">Filter by Sector</label>
          <select
            value={selectedSector}
            onChange={(e) => setSelectedSector(e.target.value)}
            className="flex h-9 w-[200px] rounded-md border border-slate-300 bg-transparent px-3 py-1 text-sm"
          >
            <option value="all">All Sectors</option>
            {availableSectors.map((sector) => (
              <option key={sector} value={sector}>
                {sector}
              </option>
            ))}
          </select>
        </div>
      </div>

      {filteredData.length > 0 && (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-muted">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Sector</th>
                <th className="px-4 py-3 text-right font-medium">Current P/E</th>
                <th className="px-4 py-3 text-right font-medium">3Y Avg P/E</th>
                <th className="px-4 py-3 text-right font-medium">Change</th>
                <th className="px-4 py-3 text-center font-medium">Trend</th>
                <th className="px-4 py-3 text-right font-medium">Volatility</th>
              </tr>
            </thead>
            <tbody>
              {filteredData
                .sort((a, b) => b.pe_change_pct - a.pe_change_pct)
                .map((trend) => (
                  <tr key={trend.sector} className="border-t hover:bg-muted/50">
                    <td className="px-4 py-3 font-medium">{trend.sector}</td>
                    <td className="px-4 py-3 text-right">{trend.current_pe?.toFixed(2) ?? "N/A"}</td>
                    <td className="px-4 py-3 text-right text-muted-foreground">
                      {trend.avg_pe_3yr?.toFixed(2) ?? "N/A"}
                    </td>
                    <td className={`px-4 py-3 text-right font-medium ${getChangeColor(trend.pe_change_pct)}`}>
                      {trend.pe_change_pct > 0 ? "+" : ""}
                      {trend.pe_change_pct?.toFixed(1) ?? "N/A"}%
                    </td>
                    <td className="px-4 py-3 text-center">{getTrendBadge(trend.trend)}</td>
                    <td className="px-4 py-3 text-right">{trend.volatility?.toFixed(1) ?? "N/A"}%</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="text-sm text-muted-foreground space-y-1">
        <p><strong>Trend Analysis:</strong> Based on P/E multiple changes vs 3-year average</p>
        <p><strong>Volatility:</strong> Standard deviation of P/E over historical period (as % of mean)</p>
        <p className="text-xs mt-2">Data source: sector_multiples_history (2019-2024)</p>
      </div>
    </div>
  );
}
