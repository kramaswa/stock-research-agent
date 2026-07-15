"use client";

import { useState, useRef } from "react";
import dynamic from "next/dynamic";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Search, TrendingUp, Newspaper, BarChart3, Loader2,
  ChevronDown, ChevronUp, Sparkles, ShieldCheck,
} from "lucide-react";
import DiscoveryCard, { type Recommendation } from "./DiscoveryCard";

const PriceChart = dynamic(() => import("./PriceChart"), { ssr: false });

type AgentStep = "init" | "quant" | "news" | "synthesis" | "done";
type Mode = "research" | "discover" | "hold";

interface AgentResult { quant?: string; news?: string; }
interface ReportData { content: string; ticker: string; company: string; }
interface ChartPoint { label: string; date: string; price: number; }
interface UserContext { risk: string; horizon: string; goal: string; }
interface HoldResult {
  content: string; ticker: string; company: string;
  current_price: number; purchase_price: number;
}
interface HoldHistoryEntry {
  id: string;
  ticker: string;
  company: string;
  signal: string;
  signalKey: string;
  risk: string;
  horizon: string;
  goal: string;
  purchasePrice: number;
  currentPrice: number;
  timestamp: string;
  content: string;
  sources: string[];
}

interface PreCheckAnswer { answer: "YES" | "NO" | "BORDERLINE"; evidence: string; }
interface EvalIssue { severity: "critical" | "major" | "minor"; section: string; description: string; }
interface EvalResult {
  overall_grade: "A" | "B" | "C" | "D" | "F";
  signal_verdict: "correct" | "likely_correct" | "overcautious" | "overaggressive" | "rule_violation";
  signal_explanation: string;
  pre_check: {
    q1: PreCheckAnswer; q2: PreCheckAnswer; q3: PreCheckAnswer; q4: PreCheckAnswer;
    profile_rule: string; signal_allowed: string; violation: string | null;
  };
  issues: EvalIssue[];
  bear_case_grade: "A" | "B" | "C" | "D";
  bear_case_feedback: string;
  section_scores: Record<string, string>;
  strengths: string[];
  improvements: string[];
  summary: string;
}

function extractSignal(content: string): { label: string; key: string } {
  // Strip bold markers then scan for each signal key — same logic as ThesisStatusBanner
  const cleaned = content.toLowerCase().replace(/\*+/g, "");
  for (const s of SIGNALS) {
    if (cleaned.includes(`signal: ${s.key}`)) return { label: s.label, key: s.key };
  }
  return { label: "Unknown", key: "unknown" };
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatHorizon(h: string) {
  if (h === "short-term") return "Short";
  if (h === "medium-term") return "Medium";
  if (h === "long-term") return "Long";
  return h;
}

function formatHistoryDate(ts: string) {
  const d = new Date(ts);
  const diff = Date.now() - d.getTime();
  if (diff < 86400000) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (diff < 172800000) return "Yesterday";
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

const GRADE_COLOR: Record<string, string> = {
  A: "text-emerald-600", B: "text-blue-600", C: "text-amber-600", D: "text-orange-600", F: "text-red-600",
};
const GRADE_BG: Record<string, string> = {
  A: "bg-emerald-50 border-emerald-200 text-emerald-800",
  B: "bg-blue-50 border-blue-200 text-blue-800",
  C: "bg-amber-50 border-amber-200 text-amber-800",
  D: "bg-orange-50 border-orange-200 text-orange-800",
  F: "bg-red-50 border-red-200 text-red-800",
};
const VERDICT_STYLE: Record<string, string> = {
  correct: "bg-emerald-50 border-emerald-200 text-emerald-800",
  likely_correct: "bg-emerald-50 border-emerald-200 text-emerald-700",
  overcautious: "bg-blue-50 border-blue-200 text-blue-800",
  overaggressive: "bg-red-50 border-red-200 text-red-800",
  rule_violation: "bg-red-50 border-red-200 text-red-800",
};
const VERDICT_LABEL: Record<string, string> = {
  correct: "Signal Correct",
  likely_correct: "Signal Likely Correct",
  overcautious: "Signal Overcautious",
  overaggressive: "Signal Overaggressive",
  rule_violation: "Signal Rule Violation",
};
const SEVERITY_STYLE: Record<string, string> = {
  critical: "bg-red-50 border-red-200 text-red-700",
  major: "bg-amber-50 border-amber-200 text-amber-700",
  minor: "bg-gray-50 border-gray-200 text-gray-600",
};
const SEVERITY_ICON: Record<string, string> = { critical: "✕", major: "!", minor: "·" };
const ANSWER_STYLE: Record<string, string> = {
  YES: "bg-red-50 text-red-700 font-semibold",
  NO: "bg-emerald-50 text-emerald-700 font-semibold",
  BORDERLINE: "bg-amber-50 text-amber-700 font-semibold",
};

function EvalPanel({
  result, loading, error, onEvaluate,
}: {
  result: EvalResult | null; loading: boolean; error: string | null; onEvaluate: () => void;
}) {
  const [showStrengths, setShowStrengths] = useState(false);

  if (!result && !loading && !error) {
    return (
      <button
        onClick={onEvaluate}
        className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-blue-600 transition-colors font-medium"
      >
        <span className="text-base">⚖</span> Evaluate analysis quality
      </button>
    );
  }
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" />
        Running quality evaluation (~20s)...
      </div>
    );
  }
  if (error) {
    return <p className="text-sm text-red-500">{error}</p>;
  }
  if (!result) return null;

  const criticalIssues = result.issues.filter((i) => i.severity === "critical");
  const majorIssues = result.issues.filter((i) => i.severity === "major");
  const minorIssues = result.issues.filter((i) => i.severity === "minor");
  const sectionEntries = Object.entries(result.section_scores);

  return (
    <div className="mt-2 border border-gray-200 rounded-xl bg-gray-50 p-4 space-y-4 text-sm">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">Quality Evaluation</p>
          <p className="text-gray-600 leading-snug max-w-lg">{result.signal_explanation}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-3xl font-bold tabular-nums ${GRADE_COLOR[result.overall_grade] ?? "text-gray-700"}`}>
            {result.overall_grade}
          </span>
          <span className={`px-2 py-0.5 text-xs font-medium rounded-full border ${VERDICT_STYLE[result.signal_verdict] ?? ""}`}>
            {VERDICT_LABEL[result.signal_verdict] ?? result.signal_verdict}
          </span>
        </div>
      </div>

      {/* Pre-check table */}
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Pre-Check Verification</p>
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden divide-y divide-gray-100">
          {(["q1", "q2", "q3", "q4"] as const).map((q, i) => {
            const labels = ["Price run >30/50%", "Valuation stretched", "Bull assumptions req.", "Margin of safety"];
            const item = result.pre_check[q];
            return (
              <div key={q} className="flex items-start gap-3 px-3 py-2">
                <span className="text-xs text-gray-400 font-mono w-4 flex-shrink-0 mt-0.5">Q{i + 1}</span>
                <span className="text-xs text-gray-500 w-32 flex-shrink-0">{labels[i]}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded flex-shrink-0 ${ANSWER_STYLE[item.answer] ?? ""}`}>
                  {item.answer}
                </span>
                <span className="text-xs text-gray-500 leading-snug">{item.evidence}</span>
              </div>
            );
          })}
        </div>
        <div className="mt-1.5 px-1 space-y-0.5">
          <p className="text-xs text-gray-500"><span className="font-medium">Rule:</span> {result.pre_check.profile_rule}</p>
          <p className="text-xs text-gray-500"><span className="font-medium">Allowed signals:</span> {result.pre_check.signal_allowed}</p>
          {result.pre_check.violation && (
            <p className="text-xs text-red-600 font-medium">⚠ Violation: {result.pre_check.violation}</p>
          )}
        </div>
      </div>

      {/* Issues */}
      {result.issues.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
            Issues ({result.issues.length})
          </p>
          <div className="space-y-1.5">
            {[...criticalIssues, ...majorIssues, ...minorIssues].map((issue, idx) => (
              <div key={idx} className={`flex items-start gap-2 px-3 py-2 rounded-lg border text-xs ${SEVERITY_STYLE[issue.severity] ?? ""}`}>
                <span className="font-bold flex-shrink-0 w-3">{SEVERITY_ICON[issue.severity]}</span>
                <span className="font-semibold flex-shrink-0 w-12 capitalize">{issue.severity}</span>
                <span className="text-gray-500 flex-shrink-0 w-20 truncate">{issue.section}</span>
                <span className="leading-snug">{issue.description}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Section scores */}
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Section Scores</p>
        <div className="flex flex-wrap gap-2">
          {sectionEntries.map(([section, grade]) => (
            <div key={section} className={`flex items-center gap-1.5 px-2 py-1 rounded-lg border text-xs ${GRADE_BG[grade] ?? "bg-gray-50 border-gray-200 text-gray-700"}`}>
              <span className="font-bold">{grade}</span>
              <span className="capitalize">{section.replace(/_/g, " ")}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Bear case */}
      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Bear Case</p>
        <div className="flex items-start gap-2">
          <span className={`px-1.5 py-0.5 text-xs font-bold rounded border ${GRADE_BG[result.bear_case_grade] ?? ""}`}>
            {result.bear_case_grade}
          </span>
          <p className="text-xs text-gray-600 leading-snug">{result.bear_case_feedback}</p>
        </div>
      </div>

      {/* Improvements */}
      {result.improvements.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Suggested Improvements</p>
          <ul className="space-y-1">
            {result.improvements.map((imp, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-gray-600">
                <span className="text-blue-400 flex-shrink-0 mt-0.5">›</span>
                {imp}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Strengths (collapsed) */}
      {result.strengths.length > 0 && (
        <div>
          <button
            onClick={() => setShowStrengths(!showStrengths)}
            className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1 transition-colors"
          >
            {showStrengths ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {showStrengths ? "Hide" : "Show"} strengths ({result.strengths.length})
          </button>
          {showStrengths && (
            <ul className="mt-1.5 space-y-1">
              {result.strengths.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-emerald-700">
                  <span className="flex-shrink-0 mt-0.5">✓</span>
                  {s}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Summary */}
      <p className="text-xs text-gray-500 leading-relaxed border-t border-gray-200 pt-3">{result.summary}</p>
    </div>
  );
}

function HoldCheckHistory({
  history, onSelect, onRemove, onClear,
}: {
  history: HoldHistoryEntry[];
  onSelect: (entry: HoldHistoryEntry) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
}) {
  if (history.length === 0) return null;
  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Recent Hold Checks</p>
        <button onClick={onClear} className="text-xs text-gray-400 hover:text-gray-600 transition-colors">Clear all</button>
      </div>
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden divide-y divide-gray-50">
        {history.map((entry) => {
          const sig = SIGNALS.find((s) => s.key === entry.signalKey);
          return (
            <div
              key={entry.id}
              onClick={() => onSelect(entry)}
              className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 cursor-pointer group transition-colors"
            >
              <span className="font-bold text-sm text-gray-900 w-14 flex-shrink-0 font-mono">{entry.ticker}</span>
              <span className={`flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-full border flex-shrink-0 ${sig?.style ?? "bg-gray-50 border-gray-200"}`}>
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${sig?.dot ?? "bg-gray-400"}`} />
                <span className={sig?.text ?? "text-gray-600"}>{entry.signal}</span>
              </span>
              <span className="text-xs text-gray-400 flex-1 truncate">
                {capitalize(entry.risk)} · {formatHorizon(entry.horizon)} · {capitalize(entry.goal)}
              </span>
              <span className="text-xs text-gray-400 flex-shrink-0 tabular-nums">{formatHistoryDate(entry.timestamp)}</span>
              <button
                onClick={(e) => { e.stopPropagation(); onRemove(entry.id); }}
                className="opacity-0 group-hover:opacity-100 text-gray-300 hover:text-gray-500 transition-opacity text-base leading-none ml-1 flex-shrink-0"
                aria-label="Remove"
              >×</button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ToggleGroup({
  label, options, value, onChange, disabled,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-400 font-medium whitespace-nowrap">{label}</span>
      <div className="flex rounded-lg border border-gray-200 overflow-hidden">
        {options.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            disabled={disabled}
            className={`px-3 py-1.5 text-xs font-medium transition-colors whitespace-nowrap
              ${value === opt.value ? "bg-blue-600 text-white" : "bg-white text-gray-500 hover:bg-gray-50"}
              disabled:opacity-50 disabled:cursor-not-allowed border-r border-gray-200 last:border-r-0`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

const STEP_ORDER: AgentStep[] = ["init", "quant", "synthesis", "done"];
const STEP_META: Record<AgentStep, { label: string }> = {
  init: { label: "Looking up ticker" },
  quant: { label: "Running agents in parallel" },
  news: { label: "Running agents in parallel" },
  synthesis: { label: "Synthesizing report" },
  done: { label: "Complete" },
};

function StepIndicator({ step, currentStep, message }: {
  step: AgentStep; currentStep: AgentStep | null; message?: string;
}) {
  const stepIndex = STEP_ORDER.indexOf(step);
  const currentIndex = currentStep ? STEP_ORDER.indexOf(currentStep) : -1;
  const isDone = currentIndex > stepIndex;
  const isActive = currentStep === step;
  const isPending = currentIndex < stepIndex;
  return (
    <div className="flex items-center gap-3 py-2">
      <div className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-medium transition-all
        ${isDone ? "bg-emerald-500 text-white" : ""}
        ${isActive ? "bg-blue-500 text-white ring-4 ring-blue-100" : ""}
        ${isPending ? "bg-gray-100 text-gray-400" : ""}`}>
        {isDone ? "✓" : isActive ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : stepIndex + 1}
      </div>
      <div>
        <p className={`text-sm font-medium ${isPending ? "text-gray-400" : "text-gray-800"}`}>
          {STEP_META[step].label}
        </p>
        {isActive && message && <p className="text-xs text-blue-500 mt-0.5">{message}</p>}
      </div>
    </div>
  );
}

function ProgressBar({ progress }: { progress: number }) {
  return (
    <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden mt-3">
      <div
        className="h-full bg-blue-500 rounded-full transition-all duration-700 ease-out"
        style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
      />
    </div>
  );
}

function AgentResultCard({ title, icon, content }: {
  title: string; icon: React.ReactNode; content: string;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2 text-sm font-medium text-gray-700">{icon}{title}</div>
        {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
      </button>
      {expanded && (
        <div className="px-4 pb-4 text-sm text-gray-600 border-t border-gray-100 pt-3 leading-relaxed prose prose-sm prose-gray max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

const SIGNALS = [
  {
    key: "add to position",
    label: "Add to Position",
    desc: "Business accelerating, valuation reasonable — a signal to buy more.",
    style: "bg-emerald-100 border-emerald-300",
    dot: "bg-emerald-600",
    text: "text-emerald-800",
    sub: "text-emerald-700",
  },
  {
    key: "strong hold",
    label: "Strong Hold",
    desc: "Thesis intact, business executing, good fit for your profile.",
    style: "bg-emerald-50 border-emerald-200",
    dot: "bg-emerald-500",
    text: "text-emerald-700",
    sub: "text-emerald-600",
  },
  {
    key: "consider trimming",
    label: "Consider Trimming",
    desc: "Business is fine, but the stock no longer fits your profile or position size.",
    style: "bg-amber-50 border-amber-200",
    dot: "bg-amber-400",
    text: "text-amber-700",
    sub: "text-amber-600",
  },
  {
    key: "consider exiting",
    label: "Consider Exiting",
    desc: "Thesis materially weakened or significant profile mismatch.",
    style: "bg-orange-50 border-orange-200",
    dot: "bg-orange-500",
    text: "text-orange-700",
    sub: "text-orange-600",
  },
  {
    key: "exit signal",
    label: "Exit Signal",
    desc: "The original reason for owning this no longer applies.",
    style: "bg-red-50 border-red-200",
    dot: "bg-red-500",
    text: "text-red-700",
    sub: "text-red-600",
  },
  {
    key: "hold",
    label: "Hold",
    desc: "Thesis intact with minor concerns — stay the course but monitor.",
    style: "bg-blue-50 border-blue-200",
    dot: "bg-blue-500",
    text: "text-blue-700",
    sub: "text-blue-600",
  },
];

function ThesisStatusBanner({ content }: { content: string }) {
  const lower = content.toLowerCase();
  const match = SIGNALS.find((s) => lower.includes(`signal: ${s.key}`));
  if (!match) return null;
  return (
    <div className={`flex items-center gap-3 border rounded-xl px-4 py-3 mb-5 ${match.style}`}>
      <div className={`w-3 h-3 rounded-full flex-shrink-0 ${match.dot}`} />
      <span className={`text-sm font-semibold ${match.text}`}>{match.label}</span>
      <span className={`text-xs ${match.sub}`}>{match.desc}</span>
    </div>
  );
}

function HowItWorks() {
  return (
    <div className="mb-8">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">How it works</p>
      <div className="grid gap-3 sm:grid-cols-3 mb-3">
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-3.5 h-3.5 text-blue-500" />
            </div>
            <span className="text-sm font-semibold text-gray-800">Discover</span>
          </div>
          <p className="text-xs text-gray-500 leading-relaxed">Describe what you&apos;re looking for in plain English. An AI agent fetches real data for candidates and returns the best matches with supporting evidence.</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
              <Search className="w-3.5 h-3.5 text-blue-500" />
            </div>
            <span className="text-sm font-semibold text-gray-800">Research</span>
          </div>
          <p className="text-xs text-gray-500 leading-relaxed">Enter a ticker and 4 agents run: quant pulls fundamentals, news analyzes sentiment, comparison benchmarks peers — all synthesized into a personalized report.</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
              <ShieldCheck className="w-3.5 h-3.5 text-blue-500" />
            </div>
            <span className="text-sm font-semibold text-gray-800">Hold Check</span>
          </div>
          <p className="text-xs text-gray-500 leading-relaxed">Already own a stock? The agent checks if your original thesis still holds and gives a clear signal: Add to Position, Strong Hold, Hold, Consider Trimming, Consider Exiting, or Exit Signal.</p>
        </div>
      </div>
      <p className="text-xs text-blue-400 mt-1">
        Claude Sonnet · Finnhub · NewsAPI · FastAPI · Next.js
      </p>
    </div>
  );
}

function friendlyError(e: unknown): string {
  if (!(e instanceof Error) || e.name === "AbortError") return "";
  if (e.message === "Failed to fetch" || e.message.toLowerCase().includes("network") || e.message.toLowerCase().includes("failed to fetch"))
    return "Unable to reach the server. Please try again in a moment.";
  return e.message || "Something went wrong. Please try again.";
}

export default function Home() {
  const [mode, setMode] = useState<Mode>("hold");

  // Research state
  const [ticker, setTicker] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState<AgentStep | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [agentResults, setAgentResults] = useState<AgentResult>({});
  const [report, setReport] = useState<ReportData | null>(null);
  const [chartData, setChartData] = useState<ChartPoint[] | null>(null);
  const [comparisonMd, setComparisonMd] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Discovery state
  const [discoveryQuery, setDiscoveryQuery] = useState("");
  const [discoveryResults, setDiscoveryResults] = useState<Recommendation[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const [discoveryAttempted, setDiscoveryAttempted] = useState(false);

  // Hold Check state
  const [holdTicker, setHoldTicker] = useState("");
  const [purchasePrice, setPurchasePrice] = useState("");
  const [holdThesis, setHoldThesis] = useState("");
  const [holdResult, setHoldResult] = useState<HoldResult | null>(null);
  const [holdLoading, setHoldLoading] = useState(false);
  const [holdStatusMsg, setHoldStatusMsg] = useState("");
  const [holdError, setHoldError] = useState<string | null>(null);
  const [holdSources, setHoldSources] = useState<string[]>([]);

  // Eval state
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  // Progress bars
  const [researchProgress, setResearchProgress] = useState(0);
  const [holdProgress, setHoldProgress] = useState(0);
  const [discoveryProgress, setDiscoveryProgress] = useState(0);

  // Shared investor profile
  const [userContext, setUserContext] = useState<UserContext>({ risk: "moderate", horizon: "long-term", goal: "growth" });

  // Hold Check history (persisted in localStorage)
  const [holdHistory, setHoldHistory] = useState<HoldHistoryEntry[]>(() => {
    try { return JSON.parse(localStorage.getItem("holdCheckHistory") ?? "[]"); } catch { return []; }
  });

  const abortRef = useRef<(() => void) | null>(null);
  const discoveryTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const holdSourcesRef = useRef<string[]>([]);

  const runResearch = async (tickerArg?: string) => {
    const t = (tickerArg ?? ticker).trim().toUpperCase();
    if (!t || loading) return;
    if (!/^[A-Z]{1,5}(-[A-Z]{1,2})?$/.test(t)) {
      setError("Please enter a valid stock ticker (e.g. AAPL, NVDA, TSLA).");
      return;
    }
    if (tickerArg) setTicker(tickerArg);

    setLoading(true);
    setCurrentStep("init");
    setStatusMessage("");
    setAgentResults({});
    setReport(null);
    setChartData(null);
    setComparisonMd(null);
    setError(null);
    setResearchProgress(5);

    const params = new URLSearchParams({
      risk: userContext.risk,
      horizon: userContext.horizon,
      goal: userContext.goal,
    });
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const url = `${base}/research/${t}?${params}`;
    const controller = new AbortController();
    abortRef.current = () => controller.abort();

    try {
      const response = await fetch(url, { signal: controller.signal });
      if (response.status === 400) throw new Error("Invalid ticker symbol. Please enter a valid ticker (e.g. AAPL, NVDA, TSLA).");
      if (response.status === 429) throw new Error("You've hit the rate limit (10 requests/hour). Please wait a bit before trying again.");
      if (!response.ok) throw new Error("The server encountered an error. Please try again in a moment.");
      if (!response.body) throw new Error("Unable to reach the server. Please try again.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let completed = false;
      let streamError = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "status") {
              setCurrentStep(data.step as AgentStep);
              setStatusMessage(data.message);
              if (data.step === "init") setResearchProgress(10);
              else if (data.step === "quant") setResearchProgress(30);
              else if (data.step === "synthesis") setResearchProgress(72);
            }
            else if (data.type === "agent_result") {
              setAgentResults((prev) => {
                const updated = { ...prev, [data.agent]: data.content };
                const count = Object.keys(updated).length;
                setResearchProgress(count === 1 ? 50 : 62);
                return updated;
              });
            }
            else if (data.type === "chart_data") setChartData(data.data);
            else if (data.type === "comparison_data") setComparisonMd(data.markdown);
            else if (data.type === "report") { setReport({ content: data.content, ticker: data.ticker, company: data.company }); setCurrentStep("done"); setResearchProgress(100); completed = true; }
            else if (data.type === "done") { setResearchProgress(100); completed = true; }
            else if (data.type === "error") { setError(data.message); streamError = true; }
          } catch {}
        }
      }
      if (!completed && !streamError) setError("Analysis was interrupted. Please try again.");
    } catch (e: unknown) {
      const msg = friendlyError(e);
      if (msg) setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const runDiscovery = async () => {
    if (!discoveryQuery.trim()) return;
    setDiscovering(true);
    setDiscoveryResults([]);
    setDiscoveryError(null);
    setDiscoveryAttempted(false);
    setDiscoveryProgress(3);

    // Easing timer: starts fast, slows near 92% to avoid "stuck at 99%" feel
    if (discoveryTimerRef.current) clearInterval(discoveryTimerRef.current);
    discoveryTimerRef.current = setInterval(() => {
      setDiscoveryProgress((prev) => {
        if (prev >= 92) return prev;
        return prev + (92 - prev) * 0.055;
      });
    }, 1200);

    const params = new URLSearchParams({
      query: discoveryQuery.trim(),
      risk: userContext.risk,
      horizon: userContext.horizon,
      goal: userContext.goal,
    });
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

    try {
      const res = await fetch(`${base}/discover?${params}`);
      if (res.status === 429) throw new Error("You've hit the rate limit (10 requests/hour). Please wait a bit before trying again.");
      if (!res.ok) throw new Error("The server encountered an error. Please try again in a moment.");
      const data = await res.json();
      setDiscoveryResults(data.recommendations ?? []);
    } catch (e: unknown) {
      const msg = friendlyError(e);
      if (msg) setDiscoveryError(msg);
    } finally {
      if (discoveryTimerRef.current) clearInterval(discoveryTimerRef.current);
      setDiscoveryProgress(100);
      setDiscovering(false);
      setDiscoveryAttempted(true);
    }
  };

  const runHoldCheck = async () => {
    const t = holdTicker.trim().toUpperCase();
    if (!t) return;
    if (!/^[A-Z]{1,5}(-[A-Z]{1,2})?$/.test(t)) {
      setHoldError("Please enter a valid stock ticker (e.g. AAPL, NVDA, TSLA).");
      return;
    }
    const price = purchasePrice ? parseFloat(purchasePrice) : 0;

    setHoldLoading(true);
    setHoldResult(null);
    setHoldError(null);
    setHoldSources([]);
    holdSourcesRef.current = [];
    setEvalResult(null);
    setEvalError(null);
    setHoldStatusMsg("Starting analysis...");
    setHoldProgress(5);

    const params = new URLSearchParams({
      purchase_price: price.toString(),
      thesis: holdThesis.trim(),
      risk: userContext.risk,
      horizon: userContext.horizon,
      goal: userContext.goal,
    });
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const url = `${base}/holdcheck/${t}?${params}`;

    try {
      const response = await fetch(url);
      if (response.status === 400) throw new Error("Invalid ticker symbol. Please enter a valid ticker (e.g. AAPL, NVDA, TSLA).");
      if (response.status === 429) throw new Error("You've hit the rate limit (10 requests/hour). Please wait a bit before trying again.");
      if (!response.ok) throw new Error("The server encountered an error. Please try again in a moment.");
      if (!response.body) throw new Error("Unable to reach the server. Please try again.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let completed = false;
      let streamError = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "status") {
              setHoldStatusMsg(data.message);
              if (data.step === "quant") setHoldProgress(20);
              else if (data.step === "news") setHoldProgress(42);
              else if (data.step === "analyze") setHoldProgress(70);
            }
            else if (data.type === "data_sources") {
              const srcs = data.sources ?? [];
              setHoldSources(srcs);
              holdSourcesRef.current = srcs;
            }
            else if (data.type === "hold_result") {
              setHoldResult(data);
              setHoldProgress(100);
              completed = true;
              const { label: sigLabel, key: sigKey } = extractSignal(data.content);
              const entry: HoldHistoryEntry = {
                id: Date.now().toString(),
                ticker: data.ticker,
                company: data.company,
                signal: sigLabel,
                signalKey: sigKey,
                risk: userContext.risk,
                horizon: userContext.horizon,
                goal: userContext.goal,
                purchasePrice: price,
                currentPrice: data.current_price,
                timestamp: new Date().toISOString(),
                content: data.content,
                sources: holdSourcesRef.current,
              };
              setHoldHistory((prev) => {
                const updated = [entry, ...prev.filter((h) => h.id !== entry.id)].slice(0, 20);
                try { localStorage.setItem("holdCheckHistory", JSON.stringify(updated)); } catch {}
                return updated;
              });
            }
            else if (data.type === "done") { setHoldProgress(100); completed = true; }
            else if (data.type === "error") { setHoldError(data.message); streamError = true; }
          } catch {}
        }
      }
      if (!completed && !streamError) setHoldError("Analysis was interrupted. Please try again.");
    } catch (e: unknown) {
      const msg = friendlyError(e);
      if (msg) setHoldError(msg);
    } finally {
      setHoldLoading(false);
    }
  };

  const runEval = async () => {
    if (!holdResult) return;
    setEvalLoading(true);
    setEvalError(null);
    setEvalResult(null);
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    try {
      const res = await fetch(`${base}/holdcheck/eval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: holdResult.ticker,
          hold_check_output: holdResult.content,
          risk: userContext.risk,
          horizon: userContext.horizon,
          goal: userContext.goal,
          purchase_price: holdResult.purchase_price,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? "Evaluation failed. Please try again.");
      }
      const data: EvalResult = await res.json();
      setEvalResult(data);
    } catch (e: unknown) {
      setEvalError(e instanceof Error ? e.message : "Evaluation failed. Please try again.");
    } finally {
      setEvalLoading(false);
    }
  };

  const handleHistorySelect = (entry: HoldHistoryEntry) => {
    setHoldTicker(entry.ticker);
    setPurchasePrice(entry.purchasePrice > 0 ? entry.purchasePrice.toString() : "");
    setHoldSources(entry.sources);
    setHoldResult({
      content: entry.content,
      ticker: entry.ticker,
      company: entry.company,
      current_price: entry.currentPrice,
      purchase_price: entry.purchasePrice,
    });
  };

  const handleHistoryRemove = (id: string) => {
    setHoldHistory((prev) => {
      const updated = prev.filter((h) => h.id !== id);
      try { localStorage.setItem("holdCheckHistory", JSON.stringify(updated)); } catch {}
      return updated;
    });
  };

  const handleHistoryClear = () => {
    setHoldHistory([]);
    try { localStorage.removeItem("holdCheckHistory"); } catch {}
  };

  const handleResearchFromDiscover = (t: string) => {
    setMode("research");
    runResearch(t);
  };

  const handleHoldCheckFromDiscover = (t: string) => {
    setMode("hold");
    setHoldTicker(t);
  };

  const isAnyLoading = loading || discovering || holdLoading;

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-12">

        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-600 text-xs font-semibold px-3 py-1.5 rounded-full mb-4">
            <TrendingUp className="w-3.5 h-3.5" />
            Multi-Agent Stock Research
          </div>
          <h1 className="text-4xl font-bold text-gray-900 mb-3">Stock Research Agent</h1>
          <p className="text-gray-500 text-lg max-w-xl mx-auto">
            AI agents to help you find, analyze, and hold stocks with conviction.
          </p>
        </div>

        {/* How it works */}
        <HowItWorks />

        {/* Mode Tabs */}
        <div className="flex border-b border-gray-200 mb-6">
          {([
            { id: "hold", label: "Hold Check", fullLabel: "Hold Check", icon: <ShieldCheck className="w-3.5 h-3.5" /> },
            { id: "research", label: "Research", fullLabel: "Research a Stock", icon: <Search className="w-3.5 h-3.5" /> },
            { id: "discover", label: "Discover", fullLabel: "Discover Stocks", icon: <Sparkles className="w-3.5 h-3.5" /> },
          ] as { id: Mode; label: string; fullLabel: string; icon: React.ReactNode }[]).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setMode(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px whitespace-nowrap ${
                mode === tab.id
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab.icon}
              <span className="sm:hidden">{tab.label}</span>
              <span className="hidden sm:inline">{tab.fullLabel}</span>
            </button>
          ))}
        </div>

        {/* Research Input */}
        {mode === "research" && (
          <div className="flex gap-3 mb-6">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === "Enter" && !loading && runResearch()}
                placeholder="Ticker — AAPL, NVDA, TSLA..."
                className="w-full pl-10 pr-4 py-3.5 border border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white text-sm"
                disabled={loading}
              />
            </div>
            <button
              onClick={() => runResearch()}
              disabled={loading || !ticker.trim()}
              className="px-6 py-3.5 bg-blue-600 text-white rounded-xl font-medium text-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? "Researching..." : "Research"}
            </button>
          </div>
        )}

        {/* Discover Input */}
        {mode === "discover" && (
          <div className="mb-6">
            <div className="flex gap-3">
              <div className="flex-1 relative">
                <Sparkles className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={discoveryQuery}
                  onChange={(e) => setDiscoveryQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !discovering && runDiscovery()}
                  placeholder="e.g. high-growth tech with low debt, undervalued dividend stocks..."
                  className="w-full pl-10 pr-4 py-3.5 border border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white text-sm"
                  disabled={discovering}
                />
              </div>
              <button
                onClick={runDiscovery}
                disabled={discovering || !discoveryQuery.trim()}
                className="px-6 py-3.5 bg-blue-600 text-white rounded-xl font-medium text-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                {discovering && <Loader2 className="w-4 h-4 animate-spin" />}
                {discovering ? "Searching..." : "Discover"}
              </button>
            </div>
            {discovering && (
              <div className="mt-2 ml-1">
                <p className="text-xs text-gray-400">
                  AI is screening candidates, then running quant + news analysis — this takes ~45 seconds...
                </p>
                <ProgressBar progress={discoveryProgress} />
              </div>
            )}
          </div>
        )}

        {/* Hold Check Input */}
        {mode === "hold" && (
          <>
          <HoldCheckHistory
            history={holdHistory}
            onSelect={handleHistorySelect}
            onRemove={handleHistoryRemove}
            onClear={handleHistoryClear}
          />
          <div className="mb-6 bg-white border border-gray-200 rounded-xl p-5">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">
              Is your thesis still intact?
            </p>
            <div className="flex flex-col sm:flex-row gap-3 mb-3">
              <div className="flex gap-3 flex-1">
                <div className="relative flex-1">
                  <ShieldCheck className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={holdTicker}
                    onChange={(e) => setHoldTicker(e.target.value.toUpperCase())}
                    placeholder="Ticker — AAPL"
                    className="w-full pl-10 pr-4 py-3.5 border border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    disabled={holdLoading}
                  />
                </div>
                <div className="relative w-36">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                  <input
                    type="number"
                    value={purchasePrice}
                    onChange={(e) => setPurchasePrice(e.target.value)}
                    placeholder="Buy price"
                    min="0"
                    step="0.01"
                    className="w-full pl-7 pr-4 py-3.5 border border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    disabled={holdLoading}
                  />
                </div>
              </div>
              <button
                onClick={runHoldCheck}
                disabled={holdLoading || !holdTicker.trim()}
                className="w-full sm:w-auto px-6 py-3.5 bg-blue-600 text-white rounded-xl font-medium text-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 whitespace-nowrap"
              >
                {holdLoading && <Loader2 className="w-4 h-4 animate-spin" />}
                {holdLoading ? "Checking..." : "Check Thesis"}
              </button>
            </div>
            <textarea
              value={holdThesis}
              onChange={(e) => setHoldThesis(e.target.value)}
              placeholder="Why did you buy this? (optional) — e.g. Strong AI chip demand, expanding margins, dominant market position..."
              rows={2}
              className="w-full px-4 py-3 border border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm resize-none"
              disabled={holdLoading}
            />
            {holdLoading && (
              <div className="mt-2">
                <p className="text-xs text-blue-500">{holdStatusMsg}</p>
                <ProgressBar progress={holdProgress} />
              </div>
            )}
          </div>
          </>
        )}

        {/* Investor Profile — visible in all modes */}
        <div className="flex flex-wrap gap-4 mb-6 p-4 bg-white border border-gray-200 rounded-xl">
          <ToggleGroup
            label="Risk"
            value={userContext.risk}
            onChange={(v) => setUserContext((p) => ({ ...p, risk: v }))}
            disabled={isAnyLoading}
            options={[
              { value: "conservative", label: "Conservative" },
              { value: "moderate", label: "Moderate" },
              { value: "aggressive", label: "Aggressive" },
            ]}
          />
          <ToggleGroup
            label="Horizon"
            value={userContext.horizon}
            onChange={(v) => setUserContext((p) => ({ ...p, horizon: v }))}
            disabled={isAnyLoading}
            options={[
              { value: "short-term", label: "Short" },
              { value: "medium-term", label: "Medium" },
              { value: "long-term", label: "Long" },
            ]}
          />
          <ToggleGroup
            label="Goal"
            value={userContext.goal}
            onChange={(v) => setUserContext((p) => ({ ...p, goal: v }))}
            disabled={isAnyLoading}
            options={[
              { value: "growth", label: "Growth" },
              { value: "income", label: "Income" },
              { value: "value", label: "Value" },
            ]}
          />
        </div>

        {/* ── Discovery Results ── */}
        {mode === "discover" && (
          <>
            {discoveryError && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 text-sm flex items-start justify-between gap-3">
                <p className="text-red-700">{discoveryError}</p>
                <button onClick={runDiscovery} className="text-red-600 font-semibold underline whitespace-nowrap flex-shrink-0 hover:text-red-700">Try again</button>
              </div>
            )}
            {discoveryResults.length > 0 && (
              <div className="mb-6">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  {discoveryResults.length} Stock{discoveryResults.length !== 1 ? "s" : ""} Found
                </p>
                <div className="space-y-3">
                  {discoveryResults.map((rec) => (
                    <DiscoveryCard key={rec.ticker} rec={rec} onResearch={handleResearchFromDiscover} onHoldCheck={handleHoldCheckFromDiscover} />
                  ))}
                </div>
              </div>
            )}
            {discoveryAttempted && !discovering && discoveryResults.length === 0 && !discoveryError && (
              <div className="bg-gray-50 border border-gray-200 rounded-xl p-5 text-center text-sm text-gray-500">
                No stocks found for that query. Try something more specific — e.g. <span className="font-medium text-gray-700">"high growth tech with low debt"</span> or <span className="font-medium text-gray-700">"undervalued dividend stocks"</span>.
              </div>
            )}
          </>
        )}

        {/* ── Hold Check Results ── */}
        {mode === "hold" && (
          <>
            {holdError && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 text-sm flex items-start justify-between gap-3">
                <p className="text-red-700">{holdError}</p>
                <button onClick={runHoldCheck} className="text-red-600 font-semibold underline whitespace-nowrap flex-shrink-0 hover:text-red-700">Try again</button>
              </div>
            )}
            {holdResult && (
              <div className="bg-white border border-gray-200 rounded-xl p-6">
                <div className="flex items-center justify-between mb-5">
                  <div>
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Hold Check</p>
                    <p className="text-xl font-bold text-gray-900 mt-0.5">
                      {holdResult.ticker} — {holdResult.company}
                    </p>
                  </div>
                  {holdResult.purchase_price > 0 && holdResult.current_price > 0 && (() => {
                    const pct = ((holdResult.current_price - holdResult.purchase_price) / holdResult.purchase_price) * 100;
                    const isUp = pct >= 0;
                    return (
                      <div className={`text-right ${isUp ? "text-emerald-600" : "text-red-500"}`}>
                        <p className="text-lg font-bold">${holdResult.current_price.toFixed(2)}</p>
                        <p className="text-xs font-semibold">
                          {isUp ? "+" : ""}{pct.toFixed(1)}% from ${holdResult.purchase_price.toFixed(2)}
                        </p>
                      </div>
                    );
                  })()}
                </div>
                {holdSources.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 mb-4">
                    <span className="text-xs text-gray-400">Context:</span>
                    {holdSources.map((s) => (
                      <span key={s} className="px-2 py-0.5 text-xs bg-blue-50 text-blue-600 rounded-full border border-blue-100">
                        {s}
                      </span>
                    ))}
                  </div>
                )}
                <ThesisStatusBanner content={holdResult.content} />
                <div className="prose prose-gray max-w-none prose-headings:font-semibold prose-h2:text-lg prose-h2:text-gray-800 prose-h3:text-base prose-h3:text-gray-700 prose-p:text-gray-600 prose-li:text-gray-600 prose-strong:text-gray-800">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{holdResult.content}</ReactMarkdown>
                </div>
                <div className="mt-5 pt-4 border-t border-gray-100 space-y-3">
                  <EvalPanel
                    result={evalResult}
                    loading={evalLoading}
                    error={evalError}
                    onEvaluate={runEval}
                  />
                  <button
                    onClick={() => { setMode("research"); runResearch(holdResult.ticker); }}
                    className="text-sm text-blue-600 font-medium hover:underline block"
                  >
                    Run full research report for {holdResult.ticker} →
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        {/* ── Research Results ── */}
        {mode === "research" && (
          <>
            {loading && (
              <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Agent Pipeline</p>
                <div className="divide-y divide-gray-50">
                  {(["init", "quant", "synthesis"] as AgentStep[]).map((step) => (
                    <StepIndicator key={step} step={step} currentStep={currentStep}
                      message={currentStep === step ? statusMessage : undefined} />
                  ))}
                </div>
                <ProgressBar progress={researchProgress} />
              </div>
            )}

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 text-sm flex items-start justify-between gap-3">
                <p className="text-red-700">{error}</p>
                <button onClick={() => runResearch()} className="text-red-600 font-semibold underline whitespace-nowrap flex-shrink-0 hover:text-red-700">Try again</button>
              </div>
            )}

            {(agentResults.quant || agentResults.news) && (
              <div className="mb-6 space-y-3">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Agent Outputs</p>
                {agentResults.quant && (
                  <AgentResultCard title="Quantitative Analysis" icon={<BarChart3 className="w-4 h-4" />} content={agentResults.quant} />
                )}
                {agentResults.news && (
                  <AgentResultCard title="News & Sentiment Analysis" icon={<Newspaper className="w-4 h-4" />} content={agentResults.news} />
                )}
              </div>
            )}

            {chartData && report && <PriceChart data={chartData} ticker={report.ticker} />}

            {comparisonMd && (
              <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Peer Comparison</p>
                <div className="prose prose-gray max-w-none prose-table:w-full prose-th:bg-gray-50 prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:text-xs prose-th:font-semibold prose-th:text-gray-600 prose-td:px-3 prose-td:py-2 prose-td:text-sm prose-td:text-gray-700 prose-td:border-t prose-td:border-gray-100 overflow-x-auto">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{comparisonMd}</ReactMarkdown>
                </div>
              </div>
            )}

            {report && (
              <div className="bg-white border border-gray-200 rounded-xl p-6">
                <div className="prose prose-gray max-w-none prose-headings:font-semibold prose-h2:text-xl prose-h3:text-base prose-h3:text-gray-700 prose-p:text-gray-600 prose-li:text-gray-600 prose-strong:text-gray-800 prose-table:w-full prose-th:bg-gray-50 prose-th:px-3 prose-th:py-2 prose-th:text-left prose-th:text-sm prose-th:font-semibold prose-th:text-gray-700 prose-td:px-3 prose-td:py-2 prose-td:text-sm prose-td:text-gray-600 prose-td:border-t prose-td:border-gray-100">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.content}</ReactMarkdown>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
