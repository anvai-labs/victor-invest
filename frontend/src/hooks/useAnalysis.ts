import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getLatestAnalysis, refreshAnalysis } from "@/lib/api";
import type { AnalysisResponse, UIRefreshRequest } from "@/lib/types";

export function useAnalysis(symbol: string | null) {
  return useQuery<AnalysisResponse>({
    queryKey: ["analysis", symbol],
    queryFn: () => getLatestAnalysis(symbol!),
    enabled: !!symbol,
    staleTime: 5 * 60_000,
  });
}

export function useRefreshAnalysis(symbol: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (request: UIRefreshRequest) => refreshAnalysis(symbol!, request),
    onSuccess: () => {
      if (symbol) {
        qc.invalidateQueries({ queryKey: ["analysis", symbol] });
        qc.invalidateQueries({ queryKey: ["chart", symbol] });
      }
    },
  });
}
