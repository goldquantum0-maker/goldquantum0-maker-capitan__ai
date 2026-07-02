import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { useChat } from '../context/ChatContext';
import { useWallet } from '../context/WalletContext';
import { Send, Paperclip, Sparkles, Loader2, AlertCircle } from 'lucide-react';
import { formatMarkdown, escapeHtml } from '../utils/format';

const SUGGESTIONS = [
  { label: 'Business', text: "Give me today's top business headlines" },
  { label: 'Tech', text: 'Explain quantum computing simply' },
  { label: 'Everyday', text: 'Three easy dinner recipes' },
];

export default function ChatView({ onOpenModal, toast }) {
  const { user, isGuest } = useAuth();
  const { messages, loading, sendMessage } = useChat();
  const { closeBalance, CLOSE_PRICE, sessionPassword, setSessionPassword, refreshBalance } = useWallet();
  const [input, setInput] = useState('');
  const [pendingText, setPendingText] = useState(null);
  const [uploading, setUploading] = useState(false);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto‑resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 100) + 'px';
    }
  }, [input]);

  // When the password modal is dismissed and a session password is set, send the queued message
  useEffect(() => {
    if (sessionPassword && pendingText) {
      const text = pendingText;
      setPendingText(null);
      sendMessage(text, sessionPassword)
        .then(res => {
          if (res?.close_balance !== undefined) refreshBalance();
          if (res?.burn_tx) toast(`🔥 Burn TX: ${res.burn_tx.slice(0, 10)}...`);
        })
        .catch(() => toast('Failed to send message'));
    }
  }, [sessionPassword, pendingText, sendMessage, refreshBalance, toast]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    // If not logged in, prompt signup
    if (isGuest) {
      onOpenModal('signup');
      return;
    }

    // If wallet is locked, queue the message and ask for password
    if (user && !sessionPassword) {
      setPendingText(text);
      setInput('');
      onOpenModal('password');
      return;
    }

    setInput('');
    try {
      const res = await sendMessage(text, sessionPassword);
      if (res?.close_balance !== undefined) refreshBalance();
      if (res?.burn_tx) toast(`🔥 Burn TX: ${res.burn_tx.slice(0, 10)}...`);
    } catch (e) {
      toast('Failed to send message');
    }
  }, [input, loading, isGuest, user, sessionPassword, sendMessage, refreshBalance, onOpenModal, toast]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const useSuggestion = (text) => {
    setInput(text);
    setTimeout(() => handleSend(), 100);
  };

  const handleFileUpload = () => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.accept = '.pdf,.docx,.doc,.xls,.xlsx,.txt,.png,.jpg,.jpeg';
    inp.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      if (file.size / (1024 * 1024) > 60) {
        toast('Max file size is 60MB');
        return;
      }
      setUploading(true);
      const fd = new FormData();
      fd.append('file', file);
      try {
        const res = await fetch(
          (import.meta.env.VITE_API_URL || 'http://localhost:8000') + '/api/upload',
          {
            method: 'POST',
            headers: { Authorization: 'Bearer ' + localStorage.getItem('capitan_token') },
            body: fd,
          }
        );
        if (!res.ok) throw new Error('Upload failed');
        const data = await res.json();
        toast(`Uploaded: ${file.name}`);
        // Send the uploaded document info as a message
        sendMessage(`[Uploaded document: ${file.name}]\n\nPlease analyze this document.`, sessionPassword)
          .then(res => {
            if (res?.close_balance !== undefined) refreshBalance();
            if (res?.burn_tx) toast(`🔥 Burn TX: ${res.burn_tx.slice(0, 10)}...`);
          })
          .catch(() => toast('Failed to send upload message'));
      } catch {
        toast('Upload failed');
      } finally {
        setUploading(false);
      }
    };
    inp.click();
  };

  const greeting = ['Good morning', 'Good afternoon', 'Good evening', 'Welcome'][Math.floor(new Date().getHours() / 6) % 4];

  return (
    <div className="flex-1 flex flex-col max-w-[820px] mx-auto w-full px-5 h-full">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto pt-[70px] pb-5 space-y-4 scroll-smooth">
        {messages.length === 0 ? (
          <div className="text-center pt-16 animate-fade-slide-up">
            <h1 className="text-3xl font-bold bg-gradient-to-r from-[#00b4d8] to-[#90e0ef] bg-clip-text text-transparent">
              {greeting}
            </h1>
            <div className="flex gap-3 justify-center mt-6 flex-wrap">
              {SUGGESTIONS.map(s => (
                <button
                  key={s.label}
                  onClick={() => useSuggestion(s.text)}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-3xl border border-[var(--glass-border)] bg-[var(--glass-bg)] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:bg-[var(--accent-glow)] hover:-translate-y-0.5 transition-all backdrop-blur-xl"
                >
                  <Sparkles size={14} className="text-[var(--accent)]" />
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={`message animate-message-slide-in ${msg.role === 'user' ? 'flex justify-end' : 'flex flex-col items-start'}`}
            >
              {msg.isTyping ? (
                <div className="flex items-center gap-2 px-4 py-3 bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-[4px_18px_18px_18px] backdrop-blur-xl">
                  <div className="flex gap-1">
                    {[0, 1, 2].map(j => (
                      <span
                        key={j}
                        className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-dot-bounce"
                        style={{ animationDelay: `${j * 0.2}s` }}
                      />
                    ))}
                  </div>
                </div>
              ) : msg.role === 'user' ? (
                <div className="px-4 py-3 max-w-[78%] bg-gradient-to-br from-[#00b4d8] to-[#0096c7] text-white rounded-[18px_18px_4px_18px]">
                  {escapeHtml(msg.content)}
                </div>
              ) : (
                <div
                  className="px-4 py-3 max-w-[88%] bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-[4px_18px_18px_18px] backdrop-blur-xl text-[var(--text-primary)]"
                  dangerouslySetInnerHTML={{ __html: formatMarkdown(msg.content || '') }}
                />
              )}
            </div>
          ))
        )}
        {loading && !messages.some(m => m.isTyping) && (
          <div className="flex items-center gap-2 px-4 py-3 bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-[4px_18px_18px_18px] backdrop-blur-xl">
            <Loader2 size={14} className="animate-spin text-[var(--accent)]" />
            <span className="text-sm text-[var(--text-secondary)]">Thinking...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* CLOSE Balance Badge */}
      {user && (
        <div className="flex items-center gap-2 px-3 py-1 mb-2 bg-[var(--accent-glow)] border border-[var(--accent)] rounded-2xl text-xs text-[var(--accent)] w-fit">
          <span>⏣</span>
          <span>{closeBalance.toLocaleString()} CLOSE (${((closeBalance * CLOSE_PRICE)).toFixed(4)})</span>
        </div>
      )}

      {/* Input Area */}
      <div className="pb-5">
        <div className="flex items-end gap-2 bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-3xl px-4 py-1 focus-within:border-[var(--accent)] focus-within:shadow-[0_0_0_3px_var(--accent-glow)] transition backdrop-blur-xl">
          <button
            onClick={handleFileUpload}
            disabled={uploading}
            className="p-2 rounded-full text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--accent)] disabled:opacity-50 transition"
          >
            {uploading ? <Loader2 size={16} className="animate-spin" /> : <Paperclip size={16} />}
          </button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            placeholder="Message..."
            className="flex-1 bg-transparent border-none outline-none resize-none py-2.5 text-[var(--text-primary)] placeholder-[var(--text-tertiary)] font-sans text-sm max-h-[100px]"
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="p-2 rounded-full bg-[var(--accent)] text-white hover:bg-[var(--accent-dark)] disabled:opacity-40 transition"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}