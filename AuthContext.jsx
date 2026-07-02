import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiCall } from '../utils/api';

const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('capitan_token') || null);
  const [isGuest, setIsGuest] = useState(!localStorage.getItem('capitan_token'));
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    if (!token) { setLoading(false); return; }
    try {
      const data = await apiCall('/api/auth/me');
      setUser(data);
      setIsGuest(false);
    } catch {
      setToken(null);
      setUser(null);
      setIsGuest(true);
      localStorage.removeItem('capitan_token');
      localStorage.removeItem('capitan_user');
    }
    setLoading(false);
  }, [token]);

  useEffect(() => { refreshUser(); }, [refreshUser]);

  const login = async (email, password) => {
    const res = await apiCall('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    setToken(res.token);
    setUser(res.user);
    setIsGuest(false);
    localStorage.setItem('capitan_token', res.token);
    localStorage.setItem('capitan_user', JSON.stringify(res.user));
    return res;
  };

  const signup = async (email, password, name) => {
    const res = await apiCall('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    });
    setToken(res.token);
    setUser(res.user);
    setIsGuest(false);
    localStorage.setItem('capitan_token', res.token);
    localStorage.setItem('capitan_user', JSON.stringify(res.user));
    return res;
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    setIsGuest(true);
    localStorage.removeItem('capitan_token');
    localStorage.removeItem('capitan_user');
  };

  const founderLogin = async (code) => {
    const res = await apiCall('/api/founder', {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
    setToken(res.token);
    setUser(res.user);
    setIsGuest(false);
    localStorage.setItem('capitan_token', res.token);
    localStorage.setItem('capitan_user', JSON.stringify(res.user));
    return res;
  };

  return (
    <AuthContext.Provider value={{
      user, setUser, token, setToken, isGuest, loading,
      login, signup, logout, founderLogin, refreshUser,
    }}>
      {children}
    </AuthContext.Provider>
  );
};