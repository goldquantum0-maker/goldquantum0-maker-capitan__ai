import { useStore } from "../../store/useStore";

export function Sidebar() {
  const { sidebarOpen, toggleSidebar, activeView, setActiveView, isPro, clearChat } = useStore();

  if (!sidebarOpen) {
    return (
      <aside className="sidebar collapsed">
        <button onClick={toggleSidebar} className="icon-btn">Open</button>
      </aside>
    );
  }

  return (
    <aside className="sidebar">
      <div className="sb-header">
        <div className="logo-row">
          <span className="l">⚓</span>
          <span className="t">CAPITAN AI</span>
        </div>
        <button onClick={toggleSidebar} className="icon-btn">X</button>
      </div>

      <button className="new-chat" onClick={clearChat}>New Chat</button>

      <nav className="sb-nav">
        <button className={`nav-i ${activeView === "chat" ? "active" : ""}`} onClick={() => setActiveView("chat")}>Chat</button>
        <button className={`nav-i ${activeView === "terminal" ? "active" : ""}`} onClick={() => setActiveView("terminal")}>Research Terminal</button>
      </nav>

      <div className="sb-sec">
        <div className="sec-label">Pro</div>
        {isPro ? (
          <div className="fi">Pro Active</div>
        ) : (
          <button className="upgrade">Unlock Pro - $10/mo</button>
        )}
      </div>

      <div className="sb-footer">CLOSEAI TECHNOLOGIES</div>
    </aside>
  );
}
