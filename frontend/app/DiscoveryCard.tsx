"use client";

export interface Recommendation {
  ticker: string;
  company: string;
  match: string;
  rationale: string;
  highlight: string;
}

const matchStyle: Record<string, string> = {
  "Add to Position": "bg-emerald-100 text-emerald-800",
  "Strong Hold":     "bg-emerald-50 text-emerald-600",
  "Hold":            "bg-blue-50 text-blue-600",
  "Partial Match":   "bg-gray-100 text-gray-500",
  // legacy
  "Strong Match":    "bg-emerald-50 text-emerald-600",
  "Good Match":      "bg-blue-50 text-blue-600",
};

export default function DiscoveryCard({
  rec,
  onResearch,
}: {
  rec: Recommendation;
  onResearch: (ticker: string) => void;
}) {
  const style = matchStyle[rec.match] ?? matchStyle["Partial Match"];

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 hover:border-gray-300 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold text-gray-900">{rec.ticker}</span>
          <span className="text-sm text-gray-500">{rec.company}</span>
        </div>
        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full whitespace-nowrap ml-3 ${style}`}>
          {rec.match}
        </span>
      </div>
      <p className="text-sm text-gray-600 leading-relaxed mb-4">{rec.rationale}</p>
      <div className="flex items-center justify-between">
        <span className="text-xs text-blue-600 font-medium bg-blue-50 px-2.5 py-1 rounded-full">
          ✦ {rec.highlight}
        </span>
        <button
          onClick={() => onResearch(rec.ticker)}
          className="text-xs font-semibold text-gray-500 hover:text-blue-600 transition-colors flex items-center gap-1 ml-3"
        >
          Research this →
        </button>
      </div>
    </div>
  );
}
