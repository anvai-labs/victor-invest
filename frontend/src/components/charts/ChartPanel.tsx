import { useMemo } from "react";
import {
  ComposedChart,
  Area,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  LineChart,
  Legend,
} from "recharts";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { ChartPayload } from "@/lib/types";

interface ChartPanelProps {
  chart: ChartPayload;
}

const formatDate = (d: string) => {
  const date = new Date(d);
  return `${date.getMonth() + 1}/${date.getDate()}`;
};

const fmtPrice = (v: number) => `$${v.toFixed(2)}`;

// Shared margin so all chart plot areas align horizontally
const CHART_MARGIN = { top: 4, right: 48, bottom: 0, left: 8 };

export function ChartPanel({ chart }: ChartPanelProps) {
  // Merge candle + overlay data into a single series for the price chart
  const priceData = useMemo(
    () =>
      chart.candles.map((c, i) => {
        const ov = chart.overlays?.[i];
        return {
          date: c.date,
          open: c.open,
          close: c.close,
          high: c.high,
          low: c.low,
          fill: c.close >= c.open ? "#1b7f46" : "#b42318",
          // Overlays
          sma_20: ov?.sma_20 ?? null,
          sma_50: ov?.sma_50 ?? null,
          sma_200: ov?.sma_200 ?? null,
          ema_20: ov?.ema_20 ?? null,
          ema_50: ov?.ema_50 ?? null,
          bb_upper: ov?.bb_upper ?? null,
          bb_middle: ov?.bb_middle ?? null,
          bb_lower: ov?.bb_lower ?? null,
        };
      }),
    [chart.candles, chart.overlays],
  );

  const volumeData = useMemo(
    () =>
      chart.volume.map((v) => ({
        date: v.date,
        volume: v.volume,
        obv: v.obv,
      })),
    [chart.volume],
  );

  const macdData = useMemo(
    () =>
      chart.indicators.macd.map((m) => ({
        date: m.date,
        macd: m.macd,
        signal: m.signal,
        histogram: m.histogram,
      })),
    [chart.indicators.macd],
  );

  const rsiData = useMemo(
    () =>
      chart.indicators.rsi.map((r) => ({
        date: r.date,
        rsi: r.rsi,
      })),
    [chart.indicators.rsi],
  );

  const hasBB = priceData.some((d) => d.bb_upper != null);
  const hasSMA = priceData.some((d) => d.sma_20 != null || d.sma_50 != null || d.sma_200 != null);
  const hasEMA = priceData.some((d) => d.ema_20 != null || d.ema_50 != null);

  return (
    <div className="flex flex-col gap-4">
      {/* Price + Overlays */}
      <Card>
        <CardHeader>
          <CardTitle>Price - {chart.symbol}</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={priceData} syncId="chart" margin={CHART_MARGIN}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" tickFormatter={formatDate} fontSize={11} tick={false} height={4} />
              <YAxis domain={["auto", "auto"]} fontSize={11} tickFormatter={fmtPrice} />
              <Tooltip
                labelFormatter={(l) => String(l)}
                formatter={(value: unknown, name: string) => {
                  if (value == null) return ["\u2014", name];
                  const num = Number(value);
                  return [isNaN(num) ? String(value) : fmtPrice(num), name];
                }}
              />
              <Legend verticalAlign="top" height={28} iconSize={10} wrapperStyle={{ fontSize: 11 }} />

              {/* Bollinger Bands (shaded area) */}
              {hasBB && (
                <>
                  <Area
                    type="monotone"
                    dataKey="bb_upper"
                    stroke="none"
                    fill="#94a3b8"
                    fillOpacity={0.1}
                    connectNulls
                    name="BB Upper"
                    dot={false}
                    legendType="none"
                  />
                  <Area
                    type="monotone"
                    dataKey="bb_lower"
                    stroke="none"
                    fill="#ffffff"
                    fillOpacity={1}
                    connectNulls
                    name="BB Lower"
                    dot={false}
                    legendType="none"
                  />
                  <Line
                    type="monotone"
                    dataKey="bb_upper"
                    stroke="#94a3b8"
                    dot={false}
                    strokeWidth={1}
                    strokeDasharray="4 2"
                    name="BB Upper"
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="bb_lower"
                    stroke="#94a3b8"
                    dot={false}
                    strokeWidth={1}
                    strokeDasharray="4 2"
                    name="BB Lower"
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="bb_middle"
                    stroke="#94a3b8"
                    dot={false}
                    strokeWidth={1}
                    name="BB Mid"
                    connectNulls
                  />
                </>
              )}

              {/* Close price */}
              <Line
                type="monotone"
                dataKey="close"
                stroke="#005f73"
                dot={false}
                strokeWidth={2}
                name="Close"
              />

              {/* SMAs */}
              {hasSMA && (
                <>
                  <Line type="monotone" dataKey="sma_20" stroke="#f59e0b" dot={false} strokeWidth={1} name="SMA 20" connectNulls />
                  <Line type="monotone" dataKey="sma_50" stroke="#8b5cf6" dot={false} strokeWidth={1} name="SMA 50" connectNulls />
                  <Line type="monotone" dataKey="sma_200" stroke="#ef4444" dot={false} strokeWidth={1} name="SMA 200" connectNulls />
                </>
              )}

              {/* EMAs */}
              {hasEMA && (
                <>
                  <Line type="monotone" dataKey="ema_20" stroke="#06b6d4" dot={false} strokeWidth={1} strokeDasharray="6 3" name="EMA 20" connectNulls />
                  <Line type="monotone" dataKey="ema_50" stroke="#ec4899" dot={false} strokeWidth={1} strokeDasharray="6 3" name="EMA 50" connectNulls />
                </>
              )}
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
          <ResponsiveContainer width="100%" height={160}>
            <ComposedChart data={volumeData} syncId="chart" margin={CHART_MARGIN}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" tickFormatter={formatDate} fontSize={11} tick={false} height={4} />
              <YAxis yAxisId="vol" orientation="left" fontSize={11} />
              <YAxis yAxisId="obv" orientation="right" fontSize={11} />
              <Tooltip labelFormatter={(l) => String(l)} />
              <Legend verticalAlign="top" height={24} iconSize={10} wrapperStyle={{ fontSize: 11 }} />
              <Bar yAxisId="vol" dataKey="volume" fill="#94a3b8" opacity={0.5} barSize={3} name="Volume" />
              <Line yAxisId="obv" type="monotone" dataKey="obv" stroke="#005f73" dot={false} strokeWidth={1.5} name="OBV" />
            </ComposedChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* MACD */}
      {macdData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>MACD</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={160}>
              <ComposedChart data={macdData} syncId="chart" margin={CHART_MARGIN}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="date" tickFormatter={formatDate} fontSize={11} tick={false} height={4} />
                <YAxis fontSize={11} />
                <Tooltip labelFormatter={(l) => String(l)} />
                <Legend verticalAlign="top" height={24} iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine y={0} stroke="#94a3b8" />
                <Bar dataKey="histogram" barSize={3} fill="#94a3b8" opacity={0.6} name="Histogram" />
                <Line type="monotone" dataKey="macd" stroke="#005f73" dot={false} strokeWidth={1.5} name="MACD" />
                <Line type="monotone" dataKey="signal" stroke="#b42318" dot={false} strokeWidth={1.5} name="Signal" />
              </ComposedChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* RSI */}
      {rsiData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>RSI (14)</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={rsiData} syncId="chart" margin={CHART_MARGIN}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="date" tickFormatter={formatDate} fontSize={11} />
                <YAxis domain={[0, 100]} fontSize={11} />
                <Tooltip labelFormatter={(l) => String(l)} />
                <ReferenceLine y={70} stroke="#b42318" strokeDasharray="3 3" label={{ value: "70", position: "right", fontSize: 10 }} />
                <ReferenceLine y={30} stroke="#1b7f46" strokeDasharray="3 3" label={{ value: "30", position: "right", fontSize: 10 }} />
                <Line type="monotone" dataKey="rsi" stroke="#005f73" dot={false} strokeWidth={2} name="RSI" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
