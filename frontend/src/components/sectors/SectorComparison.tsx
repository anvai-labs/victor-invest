import { useEffect, useState } from "react";

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

  const metrics = [
    { value: "pe", label: "P/E Ratio" },
    { value: "ps", label: "P/S Ratio" },
    { value: "pb", label: "P/B Ratio" },
    { value: "ev_ebitda", label: "EV/EBITDA" },
  ];

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
      .catch(() => {
        setError("Failed to load comparison data");
        setLoading(false);
      });
  }, [selectedSectors, metric]);

  const handleSectorToggle = (sector: string) => {
    if (selectedSectors.includes(sector)) {
      setSelectedSectors(selectedSectors.filter((s) => s !== sector));
    } else if (selectedSectors.length < 5) {
      setSelectedSectors([...selectedSectors, sector]);
    }
  };

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
        Loading comparison data...
      </div>
    );
  }

  if (selectedSectors.length < 2) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          <div>
            <label className="text-sm font-medium mb-2 block">Metric</label>
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
              className="flex h-9 w-[200px] rounded-md border border-slate-300 bg-transparent px-3 py-1 text-sm"
            >
              {metrics.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium mb-2 block">
              Select Sectors (2-5) <span className="text-muted-foreground">({selectedSectors.length} selected)</span>
            </label>
            <div className="flex flex-wrap gap-2">
              {availableSectors.slice(0, 15).map((sector) => (
                <button
                  key={sector}
                  type="button"
                  onClick={() => handleSectorToggle(sector)}
                  className={`px-3 py-1.5 text-sm rounded-md border ${
                    selectedSectors.includes(sector)
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-slate-300 hover:bg-slate-100"
                  }`}
                >
                  {sector}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="text-center py-12 text-muted-foreground">
          Select 2-5 sectors to compare their multiples
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 items-center">
        <div>
          <label className="text-sm font-medium mb-2 block">Metric</label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            className="flex h-9 w-[200px] rounded-md border border-slate-300 bg-transparent px-3 py-1 text-sm"
          >
            {metrics.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-sm font-medium mb-2 block">
            Selected Sectors: {selectedSectors.join(", ")}
          </label>
          <div className="flex flex-wrap gap-2">
            {availableSectors.slice(0, 15).map((sector) => (
              <button
                key={sector}
                type="button"
                onClick={() => handleSectorToggle(sector)}
                className={`px-3 py-1.5 text-sm rounded-md border ${
                  selectedSectors.includes(sector)
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-slate-300 hover:bg-slate-100"
                }`}
              >
                {sector}
              </button>
            ))}
          </div>
        </div>
      </div>

      {comparisonData && (
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

      <div className="text-sm text-muted-foreground">
        Comparing {metrics.find((m) => m.value === metric)?.label || metric} across {selectedSectors.length} sectors
      </div>
    </div>
  );
}
