const SUGGESTIONS = [
  {
    title: "Investment Research",
    prompts: [
      "Analyze NVIDIA's competitive position in AI chips",
      "Generate an investment memo for a major bank",
      "What drives gold prices in this macro environment?",
    ],
  },
  {
    title: "Market Intelligence",
    prompts: [
      "Compare African fintech across Nigeria, Kenya, and South Africa",
      "What's the outlook for emerging market currencies?",
      "Summarize the latest Fed policy implications",
    ],
  },
  {
    title: "Development",
    prompts: [
      "Write a Python backtesting framework",
      "Design a real-time market data dashboard",
      "Build a DCF valuation model",
    ],
  },
];

interface WelcomeScreenProps {
  onPromptClick: (prompt: string) => void;
}

export function WelcomeScreen({ onPromptClick }: WelcomeScreenProps) {
  return (
    <div className="welcome-screen">
      <h1>How can I help today?</h1>
      <p>Institutional research, market intelligence, and strategic analysis</p>

      <div
        style={{
          display: "flex",
          gap: "16px",
          marginTop: "24px",
          flexWrap: "wrap",
          justifyContent: "center",
        }}
      >
        {SUGGESTIONS.map((section) => (
          <div
            key={section.title}
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              padding: "16px",
              width: "220px",
            }}
          >
            <h3
              style={{
                fontSize: "11px",
                color: "var(--accent)",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                marginBottom: "10px",
                fontWeight: 600,
              }}
            >
              {section.title}
            </h3>
            {section.prompts.map((prompt) => (
              <button
                key={prompt}
                onClick={() => onPromptClick(prompt)}
                style={{
                  display: "block",
                  width: "100%",
                  background: "transparent",
                  border: "none",
                  color: "var(--text-secondary)",
                  padding: "6px 0",
                  fontSize: "11px",
                  fontFamily: "inherit",
                  textAlign: "left",
                  cursor: "pointer",
                  transition: "color 0.2s",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "#fff")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "")}
              >
                {prompt}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}