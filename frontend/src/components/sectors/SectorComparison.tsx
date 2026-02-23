import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";

interface ComparisonData {
  [year: string]: {
    [sector: string]: number | null;
  };
}

interface ComparisonResponse {
  metric: string;
  sectors: string[];
  data: ComparisonData;
  years: number[];
}

export function SectorComparison() {
  const [availableSectors, setAvailableSectors] = useState<string[]>([]);
  const [selectedSectors, setSelectedSectors] = useState<string[]>([]);
  const [metric, setMetric] = useState<string>("pe");
  const [comparisonData, setComparisonData] = useState<ComparisonResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Metric options
  const metrics = [
    { value: "pe", label: "P/E Ratio" },
    { value: "ps", label: "P/S Ratio" },
    { value: "pb", label: "P/B Ratio" },
    { value: "ev_ebitda", label: "EV/EBITDA" },
  ];

  // Fetch available sectors
  useEffect(() => {
    fetch("/ui/api/sectors/multiples")
      .then((res) => res.json())
      .then((data) => {
        if (data.sectors) {
          setAvailableSectors(data.sectors);
        }
      })
      .catch((err) => setError("Failed to load sectors"));
  }, []);

  // Fetch comparison data when sectors or metric changes
  useEffect(() => {
    if (selectedSectors.length < 2) return;

    setLoading(true);
    setError(null);

    const sectorsParam = selectedSectors.join(",");
    fetch(`/ui/api/sectors/comparison?sectors=${encodeURIComponent(sectorsParam)}&metric=${metric}`)
      .then((res) => res.json())
      .then((data) => {
        setComparisonData(data);
        setLoading(false);
      })
      .catch((err) => {
        setError("Failed to load comparison data");
        setLoading(false);
      });
  }, [selectedSectors, metric]);

  const handleSectorToggle = (sector: string) => {
    if (selectedSectors.includes(sector)) {
      setSelectedSectors(selectedSectors.filter((s) => s !== sector));
    } else {
      if (selectedSectors.length < 5) {
        setSelectedSectors([...selectedSectors, sector]);
      }
    }
  };

  const getMetricLabel = (value: string) => {
    return metrics.find((m) => m.value === value)?.label || value;
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap gap-4 items-center">
        <div className="flex-1 min-w-[200px]">
          <label className="text-sm font-medium mb-1 block">Metric</label>
          <Select value={metric} onValueChange={setMetric}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {metrics.map((m) => (
                <SelectItem key={m.value} value={m.value}>
                  {m.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex-2 min-w-[300px]">
          <label className="text-sm font-medium mb-1 block">
            Select Sectors (2-5) <span className="text-muted-foreground">({selectedSectors.length} selected)</span>
          </label>
          <div className="flex flex-wrap gap-2">
            {availableSectors.slice(0, 15).map((sector) => (
              <Button
                key={sector}
                variant={selectedSectors.includes(sector) ? "default" : "outline"}
                size="sm"
                onClick={() => handleSectorToggle(sector)}
              >
                {sector}
              </Button>
            ))}
          </div>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-destructive/10 text-destructive p-4 rounded-md">
          {error}
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="text-center py-8 text-muted-foreground">
          Loading comparison data...
        </div>
      )}

      {/* Prompt State */}
      {!loading && selectedSectors.length < 2 && (
        <div className="text-center py-12 text-muted-foreground">
          <p>Select 2-5 sectors to compare their {getMetricLabel(metric)}</p>
        </div>
      )}

      {/* Comparison Table */}
      {!loading && comparisonData && selectedSectors.length >= 2 && (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-muted">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Year</th>
                {selectedSectors.map((sector) => (
                  <th key={sector} className="px-4 py-2 text-right font-medium">
                    {sector}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {comparisonData.years.slice().reverse().map((year) => (
                <tr key={year} className="border-t">
                  <td className="px-4 py-2 font-medium">{year}</td>
                  {selectedSectors.map((sector) => {
                    const value = comparisonData.data[year]?.[sector];
                    return (
                      <td key={sector} className="px-4 py-2 text-right">
                        {value !== null && value !== undefined ? value.toFixed(2) : "N/A"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Legend */}
      {comparisonData && (
        <div className="text-sm text-muted-foreground">
          <p>Comparing {getMetricLabel(metric)} across {selectedSectors.length} sectors</p>
          <p className="text-xs mt-1">Data source: sector_multiples_history table</p>
        </div>
      )}
    </div>
  );
}
