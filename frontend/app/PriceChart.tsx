"use client";

import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface ChartPoint {
  label: string;
  date: string;
  price: number;
}

export default function PriceChart({ data, ticker }: { data: ChartPoint[]; ticker: string }) {
  const first = data[0]?.price ?? 0;
  const last = data[data.length - 1]?.price ?? 0;
  const isUp = last >= first;
  const color = isUp ? "#10b981" : "#ef4444";
  const returnPct = first > 0 ? (((last - first) / first) * 100).toFixed(1) : "0.0";

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Price Performance</p>
          <p className="text-2xl font-bold text-gray-900 mt-0.5">${last.toFixed(2)}</p>
        </div>
        <div className={`text-sm font-semibold px-3 py-1.5 rounded-full ${isUp ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-500"}`}>
          {isUp ? "+" : ""}{returnPct}% (52W)
        </div>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.15} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} />
          <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "#9ca3af" }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} width={60} />
          <Tooltip
            formatter={(v) => [`$${Number(v).toFixed(2)}`, "Price"]}
            labelStyle={{ fontSize: 12, color: "#374151" }}
            contentStyle={{ borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }}
          />
          <Area type="monotone" dataKey="price" stroke={color} strokeWidth={2} fill="url(#priceGrad)" dot={{ r: 3, fill: color }} activeDot={{ r: 5 }} />
        </AreaChart>
      </ResponsiveContainer>
      <p className="text-xs text-gray-400 mt-2">Approximate prices derived from period returns. Not tick-level data.</p>
    </div>
  );
}
