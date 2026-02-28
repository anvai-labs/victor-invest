import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useState, useEffect, useRef } from "react";
import { RefreshCw, Download } from "lucide-react";

interface SectorData {
  sector: string;
  fiscal_year: number;
  pe: number;
  ps: number;
  pb: number;
  ev_ebitda?: number;
}

interface StockData {
  symbol: string;
  sector: string;
  market_cap: number;
  pe_ratio: number;
  ps_ratio: number;
  pb_ratio: number;
  rank_in_sector: number;
}

interface TimelineResponse {
  data: { [sector: string]: { data: SectorData[]; years: number[] } };
  sectors: string[];
  years: number[];
}

interface StockResponse {
  data: { [sector: string]: { stocks: StockData[]; count: number } };
  sectors: string[];
  total: number;
}

interface SectorTimelineProps {
  selectedSectors?: string[];
}

const SECTOR_COLORS: { [key: string]: string } = {
  "Technology": "#007AFF",
  "Health Care": "#5856D6",
  "Healthcare": "#5856D6",
  "Finance": "#34C759",
  "Financials": "#34C759",
  "Consumer Discretionary": "#FF9500",
  "Telecommunications": "#FF3B30",
  "Communication Services": "#FF3B30",
  "Industrials": "#FFCC00",
  "Consumer Staples": "#8E8E93",
  "Energy": "#AF52DE",
  "Utilities": "#32ADE6",
  "Real Estate": "#FF2D55",
};

const METRIC_LABELS: { [key: string]: string } = {
  "pe": "P/E",
  "ps": "P/S",
  "pb": "P/B",
};

export function SectorTimeline({ selectedSectors }: SectorTimelineProps) {
  const [timelineData, setTimelineData] = useState<TimelineResponse | null>(null);
  const [stockData, setStockData] = useState<StockResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string>("pe");
  const plotRefs = {
    pe: useRef<HTMLDivElement>(null),
    ps: useRef<HTMLDivElement>(null),
    pb: useRef<HTMLDivElement>(null),
  };

  useEffect(() => {
    fetchData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSectors]);

  const fetchData = async () => {
    setLoading(true);
    try {
      // Fetch timeline data
      const sectorParam = selectedSectors?.join(",");
      const timelineParams = new URLSearchParams();
      if (sectorParam) timelineParams.append("sectors", sectorParam);

      const [timelineRes, stocksRes] = await Promise.all([
        fetch(`/ui/api/sectors/timeline?${timelineParams}`),
        fetch(`/ui/api/sectors/stocks/representative?${sectorParam ? `sector=${sectorParam}` : ""}`),
      ]);

      if (!timelineRes.ok) throw new Error("Failed to fetch timeline data");
      if (!stocksRes.ok) throw new Error("Failed to fetch stock data");

      const timeline: TimelineResponse = await timelineRes.json();
      const stocks: StockResponse = await stocksRes.json();

      setTimelineData(timeline);
      setStockData(stocks);
    } catch (err) {
      console.error("Error fetching data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (timelineData) {
      // Render all plots when data loads
      ["pe", "ps", "pb"].forEach((metric) => {
        if (plotRefs[metric as keyof typeof plotRefs].current) {
          renderPlotForMetric(metric);
        }
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timelineData, stockData]);

  const renderPlotForMetric = (metric: string) => {
    const ref = plotRefs[metric as keyof typeof plotRefs];
    if (!timelineData || !ref.current) return;

    // Dynamically import Plotly
    import("plotly.js-dist-min").then((Plotly) => {
      const traces: Array<{
        x: number[];
        y: number[];
        mode: string;
        name: string;
        line?: { color: string; width: number };
        marker?: { size: number; color?: string; opacity?: number };
        hovertemplate: string;
        text?: string[];
        showlegend?: boolean;
      }> = [];

      // Add sector lines
      Object.entries(timelineData.data).forEach(([sector, info]) => {
        const color = SECTOR_COLORS[sector] || "#8E8E93";
        const years = info.data.map((d) => d.fiscal_year);
        const rawValues = info.data.map((d) => d[metric as keyof SectorData]);
        // Filter out undefined and ensure all values are numbers
        const values: number[] = rawValues.filter((v): v is number => v !== undefined);

        traces.push({
          x: years,
          y: values,
          mode: "lines+markers",
          name: sector,
          line: { color, width: 2 },
          marker: { size: 6 },
          hovertemplate: `<b>${sector}</b><br>Year: %{x}<br>${METRIC_LABELS[metric]}: %{y:.2f}x<extra></extra>`,
        });
      });

      // Add stock bubbles for 2024
      if (stockData) {
        Object.entries(stockData.data).forEach(([sector, info]) => {
          const color = SECTOR_COLORS[sector] || "#8E8E93";
          info.stocks.forEach((stock) => {
            const stockMetric = metric === "pe" ? "pe_ratio" : metric === "ps" ? "ps_ratio" : "pb_ratio";
            const metricValue = stock[stockMetric as keyof StockData];
            if (typeof metricValue === "number" && metricValue > 0) {
              const size = Math.max(10, Math.min(40, 10 + 20 * Math.log(stock.market_cap / 1e12)));
              traces.push({
                x: [2024],
                y: [metricValue],
                mode: "markers",
                name: sector,
                marker: { size, color, opacity: 0.5 } as { size: number; color: string; opacity: number },
                text: [stock.symbol],
                hovertemplate: `<b>${stock.symbol}</b><br>${sector}<br>Year: 2024<br>${METRIC_LABELS[metric]}: %{y:.2f}x<br>MCap: $${(stock.market_cap / 1e9).toFixed(0)}B<extra></extra>`,
                showlegend: false,
              });
            }
          });
        });
      }

      const layout = {
        title: `Sector ${METRIC_LABELS[metric]} Multiples Timeline`,
        xaxis: { title: "Fiscal Year" },
        yaxis: { title: "Multiple" },
        hovermode: "closest",
        legend: { orientation: "h", y: -0.15 },
        margin: { l: 60, r: 20, t: 40, b: 60 },
        height: 500,
      };

      Plotly.newPlot(ref.current, traces, layout, { responsive: true });
    });
  };

  const exportChart = () => {
    const ref = plotRefs[activeTab as keyof typeof plotRefs];
    if (!ref.current) return;
    import("plotly.js-dist-min").then((Plotly) => {
      Plotly.downloadImage(ref.current, {
        format: "png",
        width: 1600,
        height: 900,
        filename: `sector_timeline_${activeTab}_${new Date().toISOString().split("T")[0]}.png`,
      });
    });
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

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Sector Multiples Timeline</CardTitle>
            <p className="text-sm text-muted-foreground">Historical sector multiples with representative stock bubbles (2024)</p>
          </div>
          <Button variant="outline" size="sm" onClick={exportChart}>
            <Download className="h-4 w-4 mr-1" />
            Export PNG
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="pe">
          <TabsList className="grid w-full max-w-md grid-cols-3">
            <TabsTrigger value="pe" onClick={() => setActiveTab("pe")}>P/E Multiple</TabsTrigger>
            <TabsTrigger value="ps" onClick={() => setActiveTab("ps")}>P/S Multiple</TabsTrigger>
            <TabsTrigger value="pb" onClick={() => setActiveTab("pb")}>P/B Multiple</TabsTrigger>
          </TabsList>
          <TabsContent value="pe" className="mt-4">
            <div ref={plotRefs.pe} className="w-full" style={{ minHeight: "500px" }} />
          </TabsContent>
          <TabsContent value="ps" className="mt-4">
            <div ref={plotRefs.ps} className="w-full" style={{ minHeight: "500px" }} />
          </TabsContent>
          <TabsContent value="pb" className="mt-4">
            <div ref={plotRefs.pb} className="w-full" style={{ minHeight: "500px" }} />
          </TabsContent>
        </Tabs>
        {stockData && (
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="text-sm text-muted-foreground">Showing representative stocks for:</span>
            {stockData.sectors.slice(0, 5).map((s) => (
              <Badge key={s} variant="default">{s}</Badge>
            ))}
            {stockData.sectors.length > 5 && <Badge variant="default">+{stockData.sectors.length - 5} more</Badge>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
