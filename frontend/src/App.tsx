import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Header } from "@/components/layout/Header";
import { SymbolSearch } from "@/components/search/SymbolSearch";
import { SummaryTab } from "@/components/analysis/SummaryTab";
import { FundamentalTab } from "@/components/analysis/FundamentalTab";
import { TechnicalTab } from "@/components/analysis/TechnicalTab";
import { ChartPanel } from "@/components/charts/ChartPanel";
import { RankingsTab } from "@/components/rankings/RankingsTab";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { useAnalysis, useRefreshAnalysis } from "@/hooks/useAnalysis";
import { useChart } from "@/hooks/useChart";
import { RefreshCw } from "lucide-react";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function Dashboard() {
  const [symbol, setSymbol] = useState<string | null>(null);
  const { data: analysis, isLoading, error } = useAnalysis(symbol);
  const { data: chart } = useChart(symbol);
  const refresh = useRefreshAnalysis(symbol);

  const view = analysis?.data ?? null;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 space-y-6">
      <div className="flex items-center gap-3">
        <SymbolSearch onSelect={setSymbol} />
        {symbol && (
          <Button
            variant="outline"
            size="sm"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate("standard")}
          >
            <RefreshCw
              className={`h-3.5 w-3.5 mr-1 ${refresh.isPending ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
        )}
      </div>

      {isLoading && (
        <p className="text-center text-slate-500 py-12">Loading analysis...</p>
      )}

      {error && (
        <p className="text-center text-bad py-12">
          {String(error)}
        </p>
      )}

      {view && (
        <>
          <h2 className="text-xl font-semibold">
            {view.company_name}{" "}
            <span className="text-accent">({view.symbol})</span>
            <span className="ml-2 text-sm font-normal text-slate-500">
              {view.sector} / {view.industry}
            </span>
          </h2>

          <Tabs defaultValue="summary">
            <TabsList>
              <TabsTrigger value="summary">Summary</TabsTrigger>
              <TabsTrigger value="fundamental">Fundamental</TabsTrigger>
              <TabsTrigger value="technical">Technical</TabsTrigger>
              {chart && <TabsTrigger value="charts">Charts</TabsTrigger>}
              <TabsTrigger value="rankings">Rankings</TabsTrigger>
            </TabsList>

            <TabsContent value="summary">
              <SummaryTab view={view} />
            </TabsContent>

            <TabsContent value="fundamental">
              {view.fundamental ? (
                <FundamentalTab fundamental={view.fundamental} />
              ) : (
                <p className="text-slate-500 py-8 text-center">
                  No fundamental data available.
                </p>
              )}
            </TabsContent>

            <TabsContent value="technical">
              {view.technical ? (
                <TechnicalTab technical={view.technical} />
              ) : (
                <p className="text-slate-500 py-8 text-center">
                  No technical data available.
                </p>
              )}
            </TabsContent>

            {chart && (
              <TabsContent value="charts">
                <ChartPanel chart={chart} />
              </TabsContent>
            )}

            <TabsContent value="rankings">
              <RankingsTab />
            </TabsContent>
          </Tabs>
        </>
      )}

      {!symbol && !isLoading && (
        <div className="text-center py-20 space-y-3">
          <p className="text-2xl font-semibold text-slate-400">
            Victor Research Dashboard
          </p>
          <p className="text-slate-500">
            Search for a symbol above to view analysis, or browse the Rankings tab.
          </p>
          <div className="pt-4">
            <Tabs defaultValue="rankings">
              <TabsList>
                <TabsTrigger value="rankings">Rankings</TabsTrigger>
              </TabsList>
              <TabsContent value="rankings">
                <RankingsTab />
              </TabsContent>
            </Tabs>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Header />
      <Dashboard />
    </QueryClientProvider>
  );
}
