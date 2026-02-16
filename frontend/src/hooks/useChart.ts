import { useQuery } from "@tanstack/react-query";
import { getChart } from "@/lib/api";
import type { ChartPayload } from "@/lib/types";

export function useChart(symbol: string | null, days = 180) {
  return useQuery<ChartPayload>({
    queryKey: ["chart", symbol, days],
    queryFn: () => getChart(symbol!, days),
    enabled: !!symbol,
    staleTime: 10 * 60_000,
  });
}
