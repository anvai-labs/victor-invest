import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import { RefreshCw, TrendingUp, TrendingDown, Minus } from "lucide-react";

interface SectorData {
  sector: string;
  fiscal_year: number;
  pe: number;
  ps: number;
  pb: number;
  ev_ebitda?: number;
  sample_size: number;
}

interface SectorOverviewProps {
  onSectorSelect?: (sector: string) => void;
}

export function SectorOverview({ onSectorSelect }: SectorOverviewProps) {
  const [data, setData] = useState<SectorData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortMetric, setSortMetric] = useState<"pe" | "ps" | "pb">("pe");

  useEffect(() => {
    fetchOverview();
  }, []);

  const fetchOverview = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/ui/api/sectors/overview`);
      if (!response.ok) throw new Error("Failed to fetch sector overview");
      const result = await response.json();
      setData(result.sectors || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const sortedData = [...data].sort((a, b) => b[sortMetric] - a[sortMetric]);

  const getTrendIcon = (value: number) => {
    if (value > 25) return <TrendingUp className="h-4 w-4 text-red-500" />;
    if (value < 15) return <TrendingDown className="h-4 w-4 text-green-500" />;
    return <Minus className="h-4 w-4 text-gray-400" />;
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-red-500">
          Error loading sector data: {error}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Sector Multiples Overview</CardTitle>
            <p className="text-sm text-muted-foreground">Current valuation multiples by sector</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={fetchOverview}>
              <RefreshCw className="h-4 w-4 mr-1" />
              Refresh
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left p-2 font-medium">Sector</th>
                <th className="text-right p-2 font-medium cursor-pointer hover:bg-muted/50" onClick={() => setSortMetric("pe")}>
                  P/E {sortMetric === "pe" && "↓"}
                </th>
                <th className="text-right p-2 font-medium cursor-pointer hover:bg-muted/50" onClick={() => setSortMetric("ps")}>
                  P/S {sortMetric === "ps" && "↓"}
                </th>
                <th className="text-right p-2 font-medium cursor-pointer hover:bg-muted/50" onClick={() => setSortMetric("pb")}>
                  P/B {sortMetric === "pb" && "↓"}
                </th>
                <th className="text-right p-2 font-medium">Samples</th>
                <th className="text-right p-2 font-medium">Year</th>
              </tr>
            </thead>
            <tbody>
              {sortedData.map((sector) => (
                <tr
                  key={sector.sector}
                  className="border-b hover:bg-muted/50 cursor-pointer"
                  onClick={() => onSectorSelect?.(sector.sector)}
                >
                  <td className="p-2 font-medium">{sector.sector}</td>
                  <td className="p-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {sector.pe.toFixed(2)}
                      {getTrendIcon(sector.pe)}
                    </div>
                  </td>
                  <td className="p-2 text-right">{sector.ps.toFixed(2)}</td>
                  <td className="p-2 text-right">{sector.pb.toFixed(2)}</td>
                  <td className="p-2 text-right text-sm text-muted-foreground">{sector.sample_size}</td>
                  <td className="p-2 text-right text-sm text-muted-foreground">{sector.fiscal_year}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
