import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { searchSymbols } from "@/lib/api";

export function useSymbolSearch(input: string) {
  const [debounced, setDebounced] = useState(input);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(input), 300);
    return () => clearTimeout(id);
  }, [input]);

  return useQuery({
    queryKey: ["symbol-search", debounced],
    queryFn: () => searchSymbols(debounced),
    enabled: debounced.length >= 1,
    staleTime: 60_000,
  });
}
