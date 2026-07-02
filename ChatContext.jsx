import React, { createContext, useContext, useState, useCallback } from 'react';
import { apiCall } from '../utils/api';

const ChatContext = createContext(null);

export const useChat = () => useContext(ChatContext);

export const ChatProvider = ({ children }) => {
  const [messages, setMessages] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [loading, setLoading] = useState(false);

  const newChat = useCallback(() => {
    setActiveChatId(null);
    setMessages([]);
  }, []);

  const sendMessage = useCallback(async (text, walletPassword) => {
    setLoading(true);
    const userMsg = { role: 'user', content: text };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);

    // Add typing placeholder
    setMessages(prev => [...prev, { role: 'assistant', content: '', isTyping: true }]);

    try {
      const body = {
        messages: updatedMessages,
        chat_id: activeChatId,
        wallet_password: walletPassword || undefined,
      };
      const res = await apiCall('/api/chat', { method: 'POST', body: JSON.stringify(body) });

      // Replace typing with actual response
      setMessages(prev => {
        const newMsgs = [...prev];
        newMsgs[newMsgs.length - 1] = {
          role: 'assistant',
          content: res.content || 'No response',
          message_id: res.message_id,
        };
        return newMsgs;
      });

      setActiveChatId(res.chat_id);
      return res;
    } catch (e) {
      setMessages(prev => {
        const newMsgs = [...prev];
        newMsgs[newMsgs.length - 1] = {
          role: 'assistant',
          content: 'Error: ' + e.message,
        };
        return newMsgs;
      });
      throw e;
    } finally {
      setLoading(false);
    }
  }, [messages, activeChatId]);

  return (
    <ChatContext.Provider value={{
      messages, setMessages, activeChatId, loading,
      newChat, sendMessage,
    }}>
      {children}
    </ChatContext.Provider>
  );
};