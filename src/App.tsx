import { useEffect, useCallback } from "react";
import { Sidebar } from "./components/Sidebar/Sidebar";
import { ChatInterface } from "./components/Chat/ChatInterface";
import { ResearchTerminal } from "./components/ResearchTerminal/ResearchTerminal";
import { StatusBar } from "./components/Layout/StatusBar";
import { useStore } from "./store/useStore";
import { fetchMarketPrices, fetchMarketNews } from "./services/api";
import "./App.css";

const POLL_INTERVAL = 60000; // 1 minute

export default function App() {
  const {
    activeView,
    isPro,
    setLivePrices,
    setMarketNews,
  } = useStore();

  const refreshMarketData = useCallback(async () => {
    if (!isPro) return;
    try {
      const [pricesRes, newsRes] = await Promise.allSettled([
        fetchMarketPrices(),
        fetchMarketNews(),
      ]);
      if (pricesRes.status === "fulfilled" && pricesRes.value.data) {
        setLivePrices(pricesRes.value.data);
      }
      if (newsRes.status === "fulfilled" && newsRes.value.data) {
        setMarketNews(newsRes.value.data);
      }
    } catch {
      // Silent fail for background updates
    }
  }, [isPro, setLivePrices, setMarketNews]);

  useEffect(() => {
    refreshMarketData();
    const interval = setInterval(refreshMarketData, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [refreshMarketData]);

  return (
    <div className="app">
      <Sidebar />
      <main className="main">
        {activeView === "chat" && <ChatInterface />}
        {activeView === "terminal" && <ResearchTerminal />}
        <StatusBar />
      </main>
    </div>
  );
}