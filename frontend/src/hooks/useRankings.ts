import { useQuery } from "@tanstack/react-query";
import { getRankings } from "@/lib/api";
import type { RankingsFilterParams, RankingsResponse } from "@/lib/types";

export function useRankings(params?: RankingsFilterParams) {
  return useQuery<RankingsResponse>({
    queryKey: ["rankings", params],
    queryFn: () => getRankings(params),
    staleTime: 15 * 60_000,
  });
}
