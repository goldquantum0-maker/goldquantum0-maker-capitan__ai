import { Sidebar } from "./components/Sidebar/Sidebar";
import { ChatInterface } from "./components/Chat/ChatInterface";
import { ResearchTerminal } from "./components/ResearchTerminal/ResearchTerminal";
import { useStore } from "./store/useStore";
import "./App.css";

export default function App() {
  const { activeView } = useStore();

  const renderView = () => {
    switch (activeView) {
      case "chat":
        return <ChatInterface />;
      case "terminal":
        return <ResearchTerminal />;
      default:
        return <ChatInterface />;
    }
  };

  return (
    <div className="app">
      <Sidebar />
      <main className="main">
        {renderView()}
      </main>
      <div className="status-bar">
        <span className="status-dot" />
        <span>CAPITAN AI</span>
      </div>
    </div>
  );
}