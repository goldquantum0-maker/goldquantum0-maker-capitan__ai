import { useStore } from "../../store/useStore";

const MODEL_LABELS: Record<string, string> = {
  fast: "Fast",
  smart: "Smart",
  deep: "Deep Think",
};

export function StatusBar() {
  const { isPro, isFounder, preferences, dailyMessageCount } = useStore();

  const modelLabel = MODEL_LABELS[preferences.model] || "Smart";
  const tierLabel = isFounder ? "Founder" : isPro ? "Pro" : "Free";
  const limit = 10;
  const remaining = isPro ? "Unlimited" : `${Math.max(0, limit - dailyMessageCount)} remaining`;

  return (
    <div className="status-bar">
      <span className="status-dot" />
      <span>CAPITAN AI</span>
      <span style={{ opacity: 0.3 }}>|</span>
      <span>{modelLabel}</span>
      {preferences.webSearch && (
        <>
          <span style={{ opacity: 0.3 }}>|</span>
          <span>Web</span>
        </>
      )}
      <span style={{ opacity: 0.3 }}>|</span>
      <span>{tierLabel}</span>
      <span style={{ opacity: 0.3 }}>|</span>
      <span style={{ color: isPro ? "var(--accent)" : "var(--text-muted)" }}>
        {remaining}
      </span>
    </div>
  );
}