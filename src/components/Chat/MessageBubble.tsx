import { memo } from "react";
import ReactMarkdown from "react-markdown";
import type { Message } from "../../store/useStore";

interface MessageBubbleProps {
  message: Message;
  isLast: boolean;
  onRetry: () => void;
}

export const MessageBubble = memo(function MessageBubble({
  message,
  isLast,
  onRetry,
}: MessageBubbleProps) {
  if (message.role === "user") {
    return (
      <div className="message user">
        <p>{message.content}</p>
      </div>
    );
  }

  const isThinking = isLast && !message.content;

  return (
    <div className="message assistant">
      <div className="msg-header">
        <span className="logo">⚓</span>
        <span>CAPITAN AI</span>
      </div>

      {isThinking ? (
        <div className="thinking-indicator">
          <div className="thinking-dots">
            <div className="thinking-dot" />
            <div className="thinking-dot" />
            <div className="thinking-dot" />
          </div>
          <span>Analyzing...</span>
        </div>
      ) : (
        <>
          <div className="msg-content">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>

          <div className="msg-actions">
            <button
              onClick={() => navigator.clipboard.writeText(message.content)}
            >
              Copy
            </button>
            <button onClick={onRetry}>Retry</button>
            <button>Save</button>
            <button>Share</button>
          </div>
        </>
      )}

      {message.content && (
        <div className="ai-note">
          CAPITAN AI can make mistakes. Verify important information.
        </div>
      )}
    </div>
  );
});