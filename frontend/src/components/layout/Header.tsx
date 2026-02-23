import { Moon, Sun, Activity, TrendingUp } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

export function Header() {
  const navigate = useNavigate();
  const [dark, setDark] = useState(() =>
    typeof window !== "undefined"
      ? document.documentElement.classList.contains("dark")
      : false,
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  useEffect(() => {
    const saved = localStorage.getItem("theme");
    if (saved === "dark" || saved === "light") {
      setDark(saved === "dark");
    } else {
      // No explicit preference: use time-of-day (dark 7pm–7am local time)
      const hour = new Date().getHours();
      const isNightTime = hour >= 19 || hour < 7;
      if (isNightTime || window.matchMedia("(prefers-color-scheme: dark)").matches) {
        setDark(true);
      }
    }
  }, []);

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4">
        <div className="flex items-center gap-6">
          <div
            className="flex items-center gap-2 cursor-pointer"
            onClick={() => navigate("/")}
          >
            <Activity className="h-5 w-5 text-accent" />
            <span className="text-lg font-semibold tracking-tight">
              Victor Research
            </span>
          </div>
          <nav className="hidden md:flex items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/")}
            >
              Symbol Analysis
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/sectors")}
            >
              <TrendingUp className="h-4 w-4 mr-1" />
              Sectors
            </Button>
          </nav>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setDark((d) => !d)}
          aria-label="Toggle dark mode"
        >
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
      </div>
    </header>
  );
}
