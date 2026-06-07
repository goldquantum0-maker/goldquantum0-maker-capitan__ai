import { useStore } from "../../store/useStore";

export function Sidebar() {
  const {
    sidebarOpen,
    toggleSidebar,
    activeView,
    setActiveView,
    isPro,
    isFounder,
    clearChat,
    watchlist,
    livePrices,
  } = useStore();

  return (
    <aside className={`sidebar ${sidebarOpen ? "" : "collapsed"}`}>
      {sidebarOpen ? (
        <>
          {/* Header */}
          <div className="sb-header">
            <div className="logo-row">
              <span className="logo-icon">⚓</span>
              <span className="logo-text">CAPITAN AI</span>
            </div>
            <button
              onClick={toggleSidebar}
              className="icon-btn"
              aria-label="Collapse sidebar"
            >
              ✕
            </button>
          </div>

          {/* New Chat */}
          <button className="new-chat-btn" onClick={clearChat}>
            + New Chat
          </button>

          {/* Navigation */}
          <nav className="sb-nav">
            <button
              className={`nav-item ${activeView === "chat" ? "active" : ""}`}
              onClick={() => setActiveView("chat")}
            >
              Chat
            </button>
            <button
              className={`nav-item ${activeView === "terminal" ? "active" : ""}`}
              onClick={() => setActiveView("terminal")}
            >
              Research Terminal
            </button>
          </nav>

          {/* Pro Section */}
          <div className="sb-section">
            <div className="section-label">Pro Features</div>
            {isPro || isFounder ? (
              <>
                <div className="feature-item">Live Market Data</div>
                <div className="feature-item">Market News</div>
                <div className="feature-item">Research Reports</div>
                <div className="feature-item">PDF Export</div>
                <div className="feature-item">API Key Management</div>
              </>
            ) : (
              <button
                className="upgrade-btn"
                onClick={() => setActiveView("chat")}
              >
                Unlock Pro — $10/month
              </button>
            )}
          </div>

          {/* Watchlist */}
          {isPro && watchlist.length > 0 && (
            <div className="sb-section">
              <div className="section-label">Watchlist</div>
              {watchlist.slice(0, 8).map((asset) => {
                const price = livePrices[asset];
                return (
                  <div key={asset} className="feature-item">
                    <span>{asset}</span>
                    {price && (
                      <span
                        style={{
                          marginLeft: "auto",
                          color: price.change_pct >= 0 ? "var(--accent)" : "var(--red)",
                          fontSize: "10px",
                        }}
                      >
                        ${price.price.toLocaleString()}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Workspace */}
          <div className="sb-section">
            <div className="section-label">Workspace</div>
            <button className="nav-item">Projects</button>
            <button className="nav-item">Saved Reports</button>
            <button className="nav-item">Settings</button>
          </div>

          {/* Footer */}
          <div className="sb-footer">CLOSEAI TECHNOLOGIES</div>
        </>
      ) : (
        <button
          onClick={toggleSidebar}
          className="icon-btn"
          aria-label="Expand sidebar"
          style={{ marginTop: "8px" }}
        >
          ☰
        </button>
      )}
    </aside>
  );
}