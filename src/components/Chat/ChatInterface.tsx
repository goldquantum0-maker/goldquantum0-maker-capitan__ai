import { useRef, useEffect, useCallback } from "react";
import { useStore } from "../../store/useStore";
import { streamChat } from "../../services/api";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { WelcomeScreen } from "./WelcomeScreen";

const generateId = () =>
  `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;

export function ChatInterface() {
  const {
    messages,
    isStreaming,
    streamError,
    addMessage,
    updateLastMessage,
    setIsStreaming,
    setStreamError,
    preferences,
    isPro,
  } = useStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSend = useCallback(
    async (content: string) => {
      if (isStreaming || !content.trim()) return;

      setStreamError(null);

      const userMessage = {
        id: generateId(),
        role: "user" as const,
        content: content.trim(),
        timestamp: Date.now(),
      };

      const assistantMessage = {
        id: generateId(),
        role: "assistant" as const,
        content: "",
        timestamp: Date.now(),
      };

      addMessage(userMessage);
      addMessage(assistantMessage);
      setIsStreaming(true);

      const allMessages = [...useStore.getState().messages].map((m) => ({
        role: m.role,
        content: m.content,
      }));

      await streamChat(
        allMessages,
        (chunk) => updateLastMessage(chunk),
        () => setIsStreaming(false),
        (error) => {
          setStreamError(error);
          setIsStreaming(false);
        }
      );
    },
    [isStreaming, addMessage, updateLastMessage, setIsStreaming, setStreamError]
  );

  const handleRetry = useCallback(() => {
    const lastUserMessage = [...messages]
      .reverse()
      .find((m) => m.role === "user");
    if (lastUserMessage) {
      const updatedMessages = messages.slice(0, -1);
      useStore.setState({ messages: updatedMessages });
      handleSend(lastUserMessage.content);
    }
  }, [messages, handleSend]);

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {messages.length === 0 && <WelcomeScreen onPromptClick={handleSend} />}

        {messages.map((message, index) => (
          <MessageBubble
            key={message.id}
            message={message}
            isLast={index === messages.length - 1}
            onRetry={handleRetry}
          />
        ))}

        {streamError && (
          <div className="message assistant" style={{ borderLeftColor: "var(--red)" }}>
            <div className="msg-header">
              <span className="logo">⚠</span> Error
            </div>
            <p style={{ color: "var(--red)" }}>
              {streamError}.{" "}
              <button
                onClick={handleRetry}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--accent)",
                  cursor: "pointer",
                  textDecoration: "underline",
                  fontFamily: "inherit",
                }}
              >
                Retry?
              </button>
            </p>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <ChatInput
        onSend={handleSend}
        disabled={isStreaming}
        placeholder={
          isStreaming
            ? "CAPITAN is thinking..."
            : `Ask anything in ${preferences.model === "deep" ? "Deep Think" : "Smart"} mode...`
        }
      />
    </div>
  );
}