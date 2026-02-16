import { Badge } from "@/components/ui/badge";
import type { UISignal } from "@/lib/types";

interface SignalBoardProps {
  signals: UISignal[];
}

export function SignalBoard({ signals }: SignalBoardProps) {
  if (!signals.length) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {signals.map((s, i) => (
        <Badge key={i} variant={s.sentiment}>
          {s.label}: {s.value}
        </Badge>
      ))}
    </div>
  );
}
