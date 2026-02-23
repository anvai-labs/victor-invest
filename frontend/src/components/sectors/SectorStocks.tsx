import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";

interface Stock {
  symbol: string;
  sector: string;
  market_cap: number;
  pe_ratio: number | null;
  ps_ratio: number | null;
  pb_ratio: number | null;
  rank_in_sector: number;
}

interface SectorStocksData {
  stocks: Stock[];
  count: number;
}

interface RepresentativeStocksResponse {
  data: {
    [sector: string]: SectorStocksData;
  };
  sectors: string[];
  total: number;
}

export function SectorStocks() {
  const [availableSectors, setAvailableSectors] = useState<string[]>([]);
  const [selectedSector, setSelectedSector] = useState<string>("all");
  const [stocksData, setStocksData] = useState<RepresentativeStocksResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [fiscalYear, setFiscalYear] = useState<number>(2024);

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

  // Fetch representative stocks
  useEffect(() => {
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({
      fiscal_year: fiscalYear.toString(),
      limit: "15",
    });

    if (selectedSector !== "all") {
      params.append("sector", selectedSector);
    }

    fetch(`/ui/api/sectors/stocks/representative?${params}`)
      .then((res) => res.json())
      .then((data) => {
        setStocksData(data);
        setLoading(false);
      })
      .catch((err) => {
        setError("Failed to load stocks data");
        setLoading(false);
      });
  }, [selectedSector, fiscalYear]);

  const formatMarketCap = (value: number) => {
    if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
    if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
    return `$${value.toFixed(2)}`;
  };

  const filterStocks = (stocks: Stock[]) => {
    if (!searchTerm) return stocks;
    return stocks.filter((stock) =>
      stock.symbol.toLowerCase().includes(searchTerm.toLowerCase())
    );
  };

  const renderStockTable = (sector: string, data: SectorStocksData) => {
    const filteredStocks = filterStocks(data.stocks);

    if (filteredStocks.length === 0) return null;

    return (
      <div key={sector} className="mb-6">
        <h3 className="text-lg font-semibold mb-3">{sector}</h3>
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-muted">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Rank</th>
                <th className="px-4 py-2 text-left font-medium">Symbol</th>
                <th className="px-4 py-2 text-right font-medium">Market Cap</th>
                <th className="px-4 py-2 text-right font-medium">P/E</th>
                <th className="px-4 py-2 text-right font-medium">P/S</th>
                <th className="px-4 py-2 text-right font-medium">P/B</th>
              </tr>
            </thead>
            <tbody>
              {filteredStocks.map((stock) => (
                <tr key={stock.symbol} className="border-t hover:bg-muted/50">
                  <td className="px-4 py-2 text-muted-foreground">#{stock.rank_in_sector}</td>
                  <td className="px-4 py-2 font-medium">{stock.symbol}</td>
                  <td className="px-4 py-2 text-right">{formatMarketCap(stock.market_cap)}</td>
                  <td className="px-4 py-2 text-right">
                    {stock.pe_ratio ? stock.pe_ratio.toFixed(2) : "N/A"}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {stock.ps_ratio ? stock.ps_ratio.toFixed(2) : "N/A"}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {stock.pb_ratio ? stock.pb_ratio.toFixed(2) : "N/A"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-sm text-muted-foreground mt-2">
          Showing {filteredStocks.length} of {data.count} stocks
        </p>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap gap-4 items-center">
        <div>
          <label className="text-sm font-medium mb-1 block">Sector</label>
          <Select value={selectedSector} onValueChange={setSelectedSector}>
            <SelectTrigger className="w-[200px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Sectors</SelectItem>
              {availableSectors.map((sector) => (
                <SelectItem key={sector} value={sector}>
                  {sector}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div>
          <label className="text-sm font-medium mb-1 block">Fiscal Year</label>
          <Select value={fiscalYear.toString()} onValueChange={(v) => setFiscalYear(parseInt(v))}>
            <SelectTrigger className="w-[120px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016].map((year) => (
                <SelectItem key={year} value={year.toString()}>
                  {year}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex-1 min-w-[200px]">
          <label className="text-sm font-medium mb-1 block">Search Symbols</label>
          <Input
            placeholder="Filter by symbol..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
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
          Loading representative stocks...
        </div>
      )}

      {/* Results */}
      {!loading && stocksData && (
        <div>
          {stocksData.total === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <p>No representative stocks found for the selected criteria</p>
            </div>
          ) : (
            <>
              {selectedSector === "all" ? (
                Object.entries(stocksData.data).map(([sector, data]) =>
                  renderStockTable(sector, data)
                )
              ) : (
                stocksData.data[selectedSector] &&
                renderStockTable(selectedSector, stocksData.data[selectedSector])
              )}
            </>
          )}
        </div>
      )}

      {/* Footer */}
      {stocksData && stocksData.total > 0 && (
        <div className="text-sm text-muted-foreground border-t pt-4">
          <p>Total: {stocksData.total} stocks across {stocksData.sectors.length} sectors</p>
          <p className="text-xs mt-1">
            Top {selectedSector === "all" ? "15" : "15"} stocks by market cap for FY{fiscalYear}
          </p>
        </div>
      )}
    </div>
  );
}
