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

const STEP_ORDER: AgentStep[] = ["init", "quant", "news", "synthesis", "done"];
const STEP_META: Record<AgentStep, { label: string }> = {
  init: { label: "Looking up ticker" },
  quant: { label: "Quantitative analysis" },
  news: { label: "News & competitors (parallel)" },
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

export default function Home() {
  const [mode, setMode] = useState<Mode>("research");

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

  // Hold Check state
  const [holdTicker, setHoldTicker] = useState("");
  const [purchasePrice, setPurchasePrice] = useState("");
  const [holdThesis, setHoldThesis] = useState("");
  const [holdResult, setHoldResult] = useState<HoldResult | null>(null);
  const [holdLoading, setHoldLoading] = useState(false);
  const [holdStatusMsg, setHoldStatusMsg] = useState("");
  const [holdError, setHoldError] = useState<string | null>(null);

  // Shared investor profile
  const [userContext, setUserContext] = useState<UserContext>({ risk: "moderate", horizon: "long-term", goal: "growth" });

  const abortRef = useRef<(() => void) | null>(null);

  const runResearch = async (tickerArg?: string) => {
    const t = (tickerArg ?? ticker).trim().toUpperCase();
    if (!t || loading) return;
    if (tickerArg) setTicker(tickerArg);

    setLoading(true);
    setCurrentStep("init");
    setStatusMessage("");
    setAgentResults({});
    setReport(null);
    setChartData(null);
    setComparisonMd(null);
    setError(null);

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
      if (!response.ok) throw new Error(`Server error: ${response.status}`);
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

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
            if (data.type === "status") { setCurrentStep(data.step as AgentStep); setStatusMessage(data.message); }
            else if (data.type === "agent_result") setAgentResults((prev) => ({ ...prev, [data.agent]: data.content }));
            else if (data.type === "chart_data") setChartData(data.data);
            else if (data.type === "comparison_data") setComparisonMd(data.markdown);
            else if (data.type === "report") { setReport({ content: data.content, ticker: data.ticker, company: data.company }); setCurrentStep("done"); }
            else if (data.type === "error") setError(data.message);
          } catch {}
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== "AbortError") setError(e.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  const runDiscovery = async () => {
    if (!discoveryQuery.trim()) return;
    setDiscovering(true);
    setDiscoveryResults([]);
    setDiscoveryError(null);

    const params = new URLSearchParams({
      query: discoveryQuery.trim(),
      risk: userContext.risk,
      horizon: userContext.horizon,
      goal: userContext.goal,
    });
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

    try {
      const res = await fetch(`${base}/discover?${params}`);
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      setDiscoveryResults(data.recommendations ?? []);
    } catch (e: unknown) {
      if (e instanceof Error) setDiscoveryError(e.message || "Discovery failed.");
    } finally {
      setDiscovering(false);
    }
  };

  const runHoldCheck = async () => {
    const t = holdTicker.trim().toUpperCase();
    if (!t) return;
    const price = purchasePrice ? parseFloat(purchasePrice) : 0;

    setHoldLoading(true);
    setHoldResult(null);
    setHoldError(null);
    setHoldStatusMsg("Starting analysis...");

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
      if (!response.ok) throw new Error(`Server error: ${response.status}`);
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

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
            if (data.type === "status") setHoldStatusMsg(data.message);
            else if (data.type === "hold_result") setHoldResult(data);
            else if (data.type === "error") setHoldError(data.message);
          } catch {}
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error) setHoldError(e.message || "Something went wrong.");
    } finally {
      setHoldLoading(false);
    }
  };

  const handleResearchFromDiscover = (t: string) => {
    setMode("research");
    runResearch(t);
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

        {/* Mode Tabs */}
        <div className="flex border-b border-gray-200 mb-6">
          {([
            { id: "research", label: "Research a Stock", icon: <Search className="w-3.5 h-3.5" /> },
            { id: "discover", label: "Discover Stocks", icon: <Sparkles className="w-3.5 h-3.5" /> },
            { id: "hold", label: "Hold Check", icon: <ShieldCheck className="w-3.5 h-3.5" /> },
          ] as { id: Mode; label: string; icon: React.ReactNode }[]).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setMode(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
                mode === tab.id
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab.icon}
              {tab.label}
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
                placeholder="Enter a ticker — AAPL, NVDA, TSLA..."
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
              <p className="text-xs text-gray-400 mt-2 ml-1">
                AI is fetching real data for candidates — this takes ~15 seconds...
              </p>
            )}
          </div>
        )}

        {/* Hold Check Input */}
        {mode === "hold" && (
          <div className="mb-6 bg-white border border-gray-200 rounded-xl p-5">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">
              Is your thesis still intact?
            </p>
            <div className="flex gap-3 mb-3">
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
              <div className="relative w-44">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                <input
                  type="number"
                  value={purchasePrice}
                  onChange={(e) => setPurchasePrice(e.target.value)}
                  placeholder="Buy price (optional)"
                  min="0"
                  step="0.01"
                  className="w-full pl-7 pr-4 py-3.5 border border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                  disabled={holdLoading}
                />
              </div>
              <button
                onClick={runHoldCheck}
                disabled={holdLoading || !holdTicker.trim()}
                className="px-6 py-3.5 bg-blue-600 text-white rounded-xl font-medium text-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2 whitespace-nowrap"
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
              <p className="text-xs text-blue-500 mt-2">{holdStatusMsg}</p>
            )}
          </div>
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
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 text-red-700 text-sm">
                {discoveryError}
              </div>
            )}
            {discoveryResults.length > 0 && (
              <div className="mb-6">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                  {discoveryResults.length} Stock{discoveryResults.length !== 1 ? "s" : ""} Found
                </p>
                <div className="space-y-3">
                  {discoveryResults.map((rec) => (
                    <DiscoveryCard key={rec.ticker} rec={rec} onResearch={handleResearchFromDiscover} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* ── Hold Check Results ── */}
        {mode === "hold" && (
          <>
            {holdError && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 text-red-700 text-sm">
                {holdError}
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
                <ThesisStatusBanner content={holdResult.content} />
                <div className="prose prose-gray max-w-none prose-headings:font-semibold prose-h2:text-lg prose-h2:text-gray-800 prose-h3:text-base prose-h3:text-gray-700 prose-p:text-gray-600 prose-li:text-gray-600 prose-strong:text-gray-800">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{holdResult.content}</ReactMarkdown>
                </div>
                <div className="mt-5 pt-4 border-t border-gray-100">
                  <button
                    onClick={() => { setMode("research"); runResearch(holdResult.ticker); }}
                    className="text-sm text-blue-600 font-medium hover:underline"
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
                  {(["init", "quant", "news", "synthesis"] as AgentStep[]).map((step) => (
                    <StepIndicator key={step} step={step} currentStep={currentStep}
                      message={currentStep === step ? statusMessage : undefined} />
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-6 text-red-700 text-sm">{error}</div>
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
