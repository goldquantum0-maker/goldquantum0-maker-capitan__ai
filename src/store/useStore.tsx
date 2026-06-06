import { create } from "zustand";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

export interface Project {
  id: string;
  name: string;
  mission: string;
  status: "active" | "completed" | "archived";
  progress: number;
  createdAt: number;
}

interface UserPreferences {
  model: "fast" | "smart" | "deep";
  webSearch: boolean;
  notificationsEnabled: boolean;
}

interface AppState {
  // Chat
  messages: Message[];
  isStreaming: boolean;
  streamError: string | null;

  // UI
  sidebarOpen: boolean;
  activeView: "chat" | "terminal" | "dashboard";

  // User
  isPro: boolean;
  isFounder: boolean;
  preferences: UserPreferences;
  dailyMessageCount: number;

  // Data
  livePrices: Record<string, { price: number; change_pct: number; source: string }>;
  marketNews: Array<{ title: string; source: string }>;
  watchlist: string[];
  projects: Record<string, Project>;

  // Actions
  addMessage: (msg: Message) => void;
  updateLastMessage: (content: string) => void;
  setIsStreaming: (v: boolean) => void;
  setStreamError: (e: string | null) => void;
  toggleSidebar: () => void;
  setActiveView: (v: "chat" | "terminal" | "dashboard") => void;
  setIsPro: (v: boolean) => void;
  setIsFounder: (v: boolean) => void;
  setLivePrices: (p: Record<string, any>) => void;
  setMarketNews: (n: Array<{ title: string; source: string }>) => void;
  addToWatchlist: (asset: string) => void;
  removeFromWatchlist: (asset: string) => void;
  clearChat: () => void;
  clearAllData: () => void;
}

const generateId = () =>
  `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;

export const useStore = create<AppState>((set, get) => ({
  messages: [],
  isStreaming: false,
  streamError: null,
  sidebarOpen: true,
  activeView: "chat",
  isPro: false,
  isFounder: false,
  preferences: {
    model: "smart",
    webSearch: true,
    notificationsEnabled: false,
  },
  dailyMessageCount: 0,
  livePrices: {},
  marketNews: [],
  watchlist: [],
  projects: {},

  addMessage: (msg) =>
    set((state) => ({
      messages: [...state.messages, msg],
    })),

  updateLastMessage: (content) =>
    set((state) => {
      const messages = [...state.messages];
      if (messages.length > 0 && messages[messages.length - 1].role === "assistant") {
        messages[messages.length - 1] = {
          ...messages[messages.length - 1],
          content,
        };
      }
      return { messages };
    }),

  setIsStreaming: (v) => set({ isStreaming: v }),
  setStreamError: (e) => set({ streamError: e }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setActiveView: (v) => set({ activeView: v }),
  setIsPro: (v) => set({ isPro: v }),
  setIsFounder: (v) => set({ isFounder: v, isPro: v }),
  setLivePrices: (p) => set({ livePrices: p }),
  setMarketNews: (n) => set({ marketNews: n }),
  
  addToWatchlist: (asset) =>
    set((state) => ({
      watchlist: state.watchlist.includes(asset)
        ? state.watchlist
        : [...state.watchlist, asset].slice(-15),
    })),

  removeFromWatchlist: (asset) =>
    set((state) => ({
      watchlist: state.watchlist.filter((a) => a !== asset),
    })),

  clearChat: () =>
    set((state) => {
      if (state.messages.length > 0) {
        const title = state.messages[0].content.slice(0, 50);
        const projectId = generateId();
        return {
          messages: [],
          projects: {
            ...state.projects,
            [projectId]: {
              id: projectId,
              name: title,
              mission: "",
              status: "active" as const,
              progress: 0,
              createdAt: Date.now(),
            },
          },
        };
      }
      return { messages: [] };
    }),

  clearAllData: () =>
    set({
      messages: [],
      watchlist: [],
      projects: {},
      dailyMessageCount: 0,
    }),
}));
