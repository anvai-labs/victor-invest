import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  LineChart,
} from "recharts";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { ChartPayload } from "@/lib/types";

interface ChartPanelProps {
  chart: ChartPayload;
}

export function ChartPanel({ chart }: ChartPanelProps) {
  const candleData = chart.candles.map((c) => ({
    date: c.date,
    open: c.open,
    close: c.close,
    high: c.high,
    low: c.low,
    // For bar chart: body of candle
    bodyLow: Math.min(c.open, c.close),
    bodyHigh: Math.max(c.open, c.close),
    body: [Math.min(c.open, c.close), Math.max(c.open, c.close)] as [number, number],
    wick: [c.low, c.high] as [number, number],
    fill: c.close >= c.open ? "#1b7f46" : "#b42318",
  }));

  const volumeData = chart.volume.map((v) => ({
    date: v.date,
    volume: v.volume,
    obv: v.obv,
  }));

  const macdData = chart.indicators.macd.map((m) => ({
    date: m.date,
    macd: m.macd,
    signal: m.signal,
    histogram: m.histogram,
  }));

  const rsiData = chart.indicators.rsi.map((r) => ({
    date: r.date,
    rsi: r.rsi,
  }));

  const formatDate = (d: string) => {
    const date = new Date(d);
    return `${date.getMonth() + 1}/${date.getDate()}`;
  };

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* Price Chart */}
      <Card className="md:col-span-2">
        <CardHeader>
          <CardTitle>Price - {chart.symbol}</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={candleData}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" tickFormatter={formatDate} fontSize={11} />
              <YAxis domain={["auto", "auto"]} fontSize={11} />
              <Tooltip
                labelFormatter={(l) => String(l)}
                formatter={(value: number) => [`$${value.toFixed(2)}`, ""]}
              />
              <Bar
                dataKey="body"
                barSize={4}
                shape={(props: unknown) => {
                  const { x, y, width, height, payload } = props as {
                    x: number;
                    y: number;
                    width: number;
                    height: number;
                    payload: { fill: string; wick: [number, number] };
                  };
                  const fill = payload.fill;
                  return (
                    <g>
                      <rect
                        x={x}
                        y={y}
                        width={width}
                        height={Math.max(height, 1)}
                        fill={fill}
                      />
                    </g>
                  );
                }}
              />
              <Line
                type="monotone"
                dataKey="high"
                stroke="transparent"
                dot={false}
                activeDot={false}
              />
              <Line
                type="monotone"
                dataKey="low"
                stroke="transparent"
                dot={false}
                activeDot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Volume + OBV */}
      <Card>
        <CardHeader>
          <CardTitle>Volume / OBV</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={volumeData}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" tickFormatter={formatDate} fontSize={11} />
              <YAxis yAxisId="vol" orientation="left" fontSize={11} />
              <YAxis yAxisId="obv" orientation="right" fontSize={11} />
              <Tooltip labelFormatter={(l) => String(l)} />
              <Bar
                yAxisId="vol"
                dataKey="volume"
                fill="#94a3b8"
                opacity={0.5}
                barSize={3}
              />
              <Line
                yAxisId="obv"
                type="monotone"
                dataKey="obv"
                stroke="#005f73"
                dot={false}
                strokeWidth={1.5}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* MACD */}
      <Card>
        <CardHeader>
          <CardTitle>MACD</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={macdData}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" tickFormatter={formatDate} fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip labelFormatter={(l) => String(l)} />
              <ReferenceLine y={0} stroke="#94a3b8" />
              <Bar
                dataKey="histogram"
                barSize={3}
                fill="#94a3b8"
                opacity={0.6}
              />
              <Line
                type="monotone"
                dataKey="macd"
                stroke="#005f73"
                dot={false}
                strokeWidth={1.5}
              />
              <Line
                type="monotone"
                dataKey="signal"
                stroke="#b42318"
                dot={false}
                strokeWidth={1.5}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* RSI */}
      <Card className="md:col-span-2">
        <CardHeader>
          <CardTitle>RSI</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={rsiData}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" tickFormatter={formatDate} fontSize={11} />
              <YAxis domain={[0, 100]} fontSize={11} />
              <Tooltip labelFormatter={(l) => String(l)} />
              <ReferenceLine y={70} stroke="#b42318" strokeDasharray="3 3" />
              <ReferenceLine y={30} stroke="#1b7f46" strokeDasharray="3 3" />
              <Line
                type="monotone"
                dataKey="rsi"
                stroke="#005f73"
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
