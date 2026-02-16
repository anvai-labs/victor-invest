import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Header } from "@/components/layout/Header";
import { SymbolSearch } from "@/components/search/SymbolSearch";
import { SummaryTab } from "@/components/analysis/SummaryTab";
import { FundamentalTab } from "@/components/analysis/FundamentalTab";
import { TechnicalTab } from "@/components/analysis/TechnicalTab";
import { PredictionsTab } from "@/components/analysis/PredictionsTab";
import { ChartPanel } from "@/components/charts/ChartPanel";
import { RankingsTab } from "@/components/rankings/RankingsTab";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { useAnalysis, useRefreshAnalysis } from "@/hooks/useAnalysis";
import { useChart } from "@/hooks/useChart";
import { usePredictions } from "@/hooks/usePredictions";
import type { UIRefreshRequest } from "@/lib/types";
import { RefreshCw, ChevronDown, ChevronUp } from "lucide-react";

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
  const [showRefreshOpts, setShowRefreshOpts] = useState(false);
  const [refreshMode, setRefreshMode] = useState<UIRefreshRequest["mode"]>("comprehensive");
  const [valuationBasis, setValuationBasis] = useState<UIRefreshRequest["valuation_basis"]>("ttm");
  const [forwardHorizon, setForwardHorizon] = useState<UIRefreshRequest["forward_horizon"]>("1y");
  const { data: analysis, isLoading, error } = useAnalysis(symbol);
  const { data: chart } = useChart(symbol);
  const { data: predictions } = usePredictions(symbol);
  const refresh = useRefreshAnalysis(symbol);

  const view = analysis?.data ?? null;

  const handleRefresh = () => {
    refresh.mutate({
      mode: refreshMode,
      valuation_basis: valuationBasis,
      forward_horizon: valuationBasis === "forward" ? forwardHorizon : undefined,
      force_refresh: true,
    });
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <SymbolSearch onSelect={setSymbol} />
        {symbol && (
          <>
            <Button
              variant="outline"
              size="sm"
              disabled={refresh.isPending}
              onClick={handleRefresh}
            >
              <RefreshCw
                className={`h-3.5 w-3.5 mr-1 ${refresh.isPending ? "animate-spin" : ""}`}
              />
              Refresh
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowRefreshOpts((s) => !s)}
              aria-label="Toggle refresh options"
            >
              {showRefreshOpts ? (
                <ChevronUp className="h-3.5 w-3.5" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5" />
              )}
            </Button>
          </>
        )}
      </div>

      {symbol && showRefreshOpts && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 px-4 py-2.5 text-sm">
          <label className="flex items-center gap-1.5">
            <span className="text-slate-500">Mode</span>
            <Select
              value={refreshMode}
              onChange={(e) => setRefreshMode(e.target.value as UIRefreshRequest["mode"])}
              className="w-36"
            >
              <option value="quick">Quick</option>
              <option value="standard">Standard</option>
              <option value="comprehensive">Comprehensive</option>
            </Select>
          </label>
          <label className="flex items-center gap-1.5">
            <span className="text-slate-500">Basis</span>
            <Select
              value={valuationBasis}
              onChange={(e) => setValuationBasis(e.target.value as UIRefreshRequest["valuation_basis"])}
              className="w-28"
            >
              <option value="ttm">TTM</option>
              <option value="forward">Forward</option>
            </Select>
          </label>
          {valuationBasis === "forward" && (
            <label className="flex items-center gap-1.5">
              <span className="text-slate-500">Horizon</span>
              <Select
                value={forwardHorizon}
                onChange={(e) => setForwardHorizon(e.target.value as UIRefreshRequest["forward_horizon"])}
                className="w-24"
              >
                <option value="1q">1Q</option>
                <option value="2q">2Q</option>
                <option value="3q">3Q</option>
                <option value="1y">1Y</option>
              </Select>
            </label>
          )}
        </div>
      )}

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
              {predictions?.predictions && predictions.predictions.length > 0 && (
                <TabsTrigger value="predictions">Predictions</TabsTrigger>
              )}
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

            <TabsContent value="predictions">
              <PredictionsTab predictions={predictions} />
            </TabsContent>

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
