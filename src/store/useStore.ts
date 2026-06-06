import { create } from "zustand";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface AppState {
  messages: Message[];
  isStreaming: boolean;
  sidebarOpen: boolean;
  activeView: "chat" | "terminal";
  isPro: boolean;
  livePrices: Record<string, any>;
  addMessage: (msg: Message) => void;
  updateLastMessage: (content: string) => void;
  setIsStreaming: (v: boolean) => void;
  toggleSidebar: () => void;
  setActiveView: (v: "chat" | "terminal") => void;
  setIsPro: (v: boolean) => void;
  setLivePrices: (p: Record<string, any>) => void;
  clearChat: () => void;
}

export const useStore = create<AppState>((set) => ({
  messages: [],
  isStreaming: false,
  sidebarOpen: true,
  activeView: "chat",
  isPro: false,
  livePrices: {},

  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  updateLastMessage: (content) =>
    set((s) => {
      const msgs = [...s.messages];
      if (msgs.length > 0) {
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content };
      }
      return { messages: msgs };
    }),
  setIsStreaming: (v) => set({ isStreaming: v }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setActiveView: (v) => set({ activeView: v }),
  setIsPro: (v) => set({ isPro: v }),
  setLivePrices: (p) => set({ livePrices: p }),
  clearChat: () => set({ messages: [] }),
}));
