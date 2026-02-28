import { useQuery } from "@tanstack/react-query";
import { getPredictions } from "@/lib/api";

export function usePredictions(symbol: string | null) {
  return useQuery({
    queryKey: ["predictions", symbol],
    queryFn: () => getPredictions(symbol!),
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000,
  });
}
