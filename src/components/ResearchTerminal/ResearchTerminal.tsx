import { useState } from "react";
import { useStore } from "../../store/useStore";
import { generateReport } from "../../services/api";

interface ReportTemplate {
  label: string;
  prompt: string;
}

interface ReportCategory {
  cat: string;
  items: ReportTemplate[];
}

const REPORTS: ReportCategory[] = [
  {
    cat: "Investment Memos",
    items: [
      {
        label: "NVIDIA Corporation (NVDA)",
        prompt:
          "Generate a comprehensive Investment Memo for NVIDIA Corporation. Include Executive Summary, Business Overview, Competitive Position, Key Risks, Bull Case, Bear Case, Financial Analysis, and Investment Conclusion. Use live market data where available.",
      },
      {
        label: "Ecobank Transnational (ETI)",
        prompt:
          "Generate a comprehensive Investment Memo for Ecobank Transnational Incorporated. Include Executive Summary, Pan-African Banking Operations, Key Risks (sovereign exposure, currency, NPLs), Bull Case, Bear Case, and Investment Conclusion.",
      },
    ],
  },
  {
    cat: "Market Research",
    items: [
      {
        label: "African Fintech Landscape",
        prompt:
          "Generate a comprehensive African Fintech Landscape Report. Cover Nigeria, Kenya, South Africa, Egypt, and Ghana. Include market sizing, key players, funding trends, regulatory developments, and growth projections.",
      },
      {
        label: "Gold Market Thesis Q3 2026",
        prompt:
          "Generate a comprehensive Gold Market Thesis for Q3 2026. Include current price analysis, macro drivers (Fed policy, inflation, dollar), technical levels, institutional positioning, scenarios, and 12-month outlook with confidence levels.",
      },
    ],
  },
  {
    cat: "Company Deep Dives",
    items: [
      {
        label: "Dangote Cement Plc",
        prompt:
          "Generate a comprehensive analysis of Dangote Cement. Include Business Overview, Nigerian Market Dominance, Pan-African Expansion, Competitive Moat, Key Risks (FX, energy costs), Financial Analysis, and Investment Conclusion.",
      },
      {
        label: "Safaricom Plc",
        prompt:
          "Generate a comprehensive analysis of Safaricom PLC. Include M-Pesa Ecosystem, Kenyan Telecom Dominance, Ethiopian Expansion, Competitive Analysis, Regulatory Environment, Financial Analysis, and Investment Conclusion.",
      },
    ],
  },
  {
    cat: "Executive Briefings",
    items: [
      {
        label: "Morning Market Brief",
        prompt:
          "Generate a comprehensive Morning Market Brief. Cover global market overview (US, Europe, Asia), key movers, economic calendar for today, top headlines, and what to watch. Use live market data.",
      },
      {
        label: "Weekly Macro Update",
        prompt:
          "Generate a comprehensive Weekly Macro Update. Cover week in review, central bank monitor (Fed, ECB, BOE, BOJ, CBN), asset class performance, key themes for next week, and risk dashboard.",
      },
    ],
  },
  {
    cat: "Client Reports",
    items: [
      {
        label: "Competitive Intelligence",
        prompt:
          "Generate a comprehensive Competitive Intelligence Report. Include Executive Summary, Company Snapshot, Competitive Landscape (strengths/weaknesses), Market Trends, Growth Opportunities, Risk Assessment, 90-Day Action Plan, and Strategic Recommendations.",
      },
      {
        label: "Market Entry Analysis",
        prompt:
          "Generate a comprehensive Market Entry Analysis. Include Executive Summary, Target Market Overview, Competitive Landscape, Regulatory Environment, Entry Strategy Options, Financial Projections, Risk Assessment, and Implementation Timeline.",
      },
      {
        label: "Strategic Recommendations",
        prompt:
          "Generate comprehensive Strategic Recommendations. Include Executive Summary, Current State Assessment, Strategic Options (with pros/cons), Prioritized Recommendations, Implementation Roadmap, Resource Requirements, and Expected Outcomes.",
      },
      {
        label: "Industry Outlook Report",
        prompt:
          "Generate a comprehensive Industry Outlook Report. Include Executive Summary, Market Size & Growth, Key Trends & Disruptors, Competitive Dynamics, Regulatory Landscape, Technology Impact, 3-5 Year Projections, and Strategic Implications.",
      },
    ],
  },
];

export function ResearchTerminal() {
  const { addMessage, updateLastMessage, setIsStreaming, isPro } = useStore();
  const [generating, setGenerating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async (label: string, prompt: string) => {
    if (generating || !isPro) return;

    setGenerating(label);
    setError(null);

    const userMsgId = `${Date.now()}-user`;
    const assistantMsgId = `${Date.now()}-assistant`;

    addMessage({
      id: userMsgId,
      role: "user",
      content: `Generate: ${label}`,
      timestamp: Date.now(),
    });
    addMessage({
      id: assistantMsgId,
      role: "assistant",
      content: "",
      timestamp: Date.now(),
    });

    try {
      const result = await generateReport(prompt, label, "research");
      if (result.content) {
        updateLastMessage(result.content);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
      updateLastMessage("Report generation failed. Please try again.");
    } finally {
      setGenerating(null);
    }
  };

  return (
    <div className="terminal-view">
      <h2>Research Terminal</h2>
      <p className="subtitle">
        Generate professional research reports in under 60 seconds.
        {!isPro && " Available with Capitan Pro."}
      </p>

      {error && (
        <div
          style={{
            background: "rgba(255,51,85,0.1)",
            border: "1px solid var(--red)",
            borderRadius: "var(--radius-sm)",
            padding: "12px",
            marginBottom: "16px",
            fontSize: "12px",
            color: "var(--red)",
          }}
        >
          {error}
        </div>
      )}

      <div className="report-grid">
        {REPORTS.map((category) => (
          <div key={category.cat} className="report-category">
            <h3>{category.cat}</h3>
            {category.items.map((item) => (
              <button
                key={item.label}
                onClick={() => handleGenerate(item.label, item.prompt)}
                disabled={generating !== null || !isPro}
                className="report-btn"
                title={!isPro ? "Requires Capitan Pro" : item.prompt.slice(0, 100)}
              >
                {generating === item.label ? "Generating..." : item.label}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}