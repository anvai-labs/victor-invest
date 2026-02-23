import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SectorOverview } from "./SectorOverview";
import { SectorTimeline } from "./SectorTimeline";
import { SectorComparison } from "./SectorComparison";
import { SectorStocks } from "./SectorStocks";
import { SectorTrends } from "./SectorTrends";
import { useState } from "react";

export function SectorAnalysisDashboard() {
  const [selectedSector, setSelectedSector] = useState<string | null>(null);
  const [selectedSectors, setSelectedSectors] = useState<string[]>([]);

  const handleSectorSelect = (sector: string) => {
    setSelectedSector(sector);
    setSelectedSectors([sector]);
  };

  const handleClearSelection = () => {
    setSelectedSector(null);
    setSelectedSectors([]);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Sector Analysis Dashboard</h1>
          <p className="text-muted-foreground">
            Interactive sector multiples analysis and comparison tools
          </p>
        </div>
        {selectedSector && (
          <button
            onClick={handleClearSelection}
            className="px-3 py-1 text-sm bg-secondary hover:bg-secondary/80 rounded-md"
          >
            Clear selection
          </button>
        )}
      </div>

      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList className="grid w-full max-w-2xl grid-cols-5">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="comparison">Comparison</TabsTrigger>
          <TabsTrigger value="stocks">Representative Stocks</TabsTrigger>
          <TabsTrigger value="trends">Trends</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <SectorOverview onSectorSelect={handleSectorSelect} />
        </TabsContent>

        <TabsContent value="timeline" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Sector Multiples Timeline</CardTitle>
              <p className="text-sm text-muted-foreground">Historical sector multiples evolution (2016-2024) with representative stock bubbles</p>
            </CardHeader>
            <CardContent>
              <SectorTimeline selectedSectors={selectedSectors.length > 0 ? selectedSectors : undefined} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="comparison" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Sector Comparison</CardTitle>
              <p className="text-sm text-muted-foreground">Compare multiples across different sectors</p>
            </CardHeader>
            <CardContent>
              <SectorComparison />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="stocks" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Representative Stocks</CardTitle>
              <p className="text-sm text-muted-foreground">Top stocks by market cap for each sector</p>
            </CardHeader>
            <CardContent>
              <SectorStocks />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="trends" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Sector Trends</CardTitle>
              <p className="text-sm text-muted-foreground">Analyze sector trends and identify patterns</p>
            </CardHeader>
            <CardContent>
              <SectorTrends />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {selectedSector && (
        <Card>
          <CardHeader>
            <CardTitle>Selected: {selectedSector}</CardTitle>
            <p className="text-sm text-muted-foreground">Detailed analysis for the selected sector</p>
          </CardHeader>
          <CardContent>
            <div className="text-center py-8 text-muted-foreground">
              <p>Detailed sector view coming soon</p>
              <p className="text-sm mt-2">Historical data, representative stocks, and trend analysis</p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
