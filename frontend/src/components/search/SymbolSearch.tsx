import { useState, useRef, useEffect } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useSymbolSearch } from "@/hooks/useSymbolSearch";

interface SymbolSearchProps {
  onSelect: (symbol: string) => void;
}

export function SymbolSearch({ onSelect }: SymbolSearchProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { data } = useSymbolSearch(query);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const results = data?.results ?? [];

  return (
    <div ref={ref} className="relative w-full max-w-md">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <Input
          placeholder="Search symbol or company..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          className="pl-9"
        />
      </div>
      {open && results.length > 0 && (
        <ul className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-md border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg">
          {results.map((r) => (
            <li key={r.symbol}>
              <button
                className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-muted dark:hover:bg-muted-dark"
                onClick={() => {
                  onSelect(r.symbol);
                  setQuery(r.symbol);
                  setOpen(false);
                }}
              >
                <span className="font-semibold text-accent min-w-[4rem]">
                  {r.symbol}
                </span>
                <span className="truncate text-slate-600 dark:text-slate-300">
                  {r.name}
                </span>
                <span className="ml-auto text-xs text-slate-400 whitespace-nowrap">
                  {r.sector}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
