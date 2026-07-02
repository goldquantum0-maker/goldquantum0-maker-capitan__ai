import React, { useState } from 'react';
import ModalWrapper from './ModalWrapper';
import { useAuth } from '../../context/AuthContext';

export default function LoginModal({ onClose, toast }) {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = async () => {
    if (!email || !password) { toast('Fill all fields'); return; }
    try {
      await login(email, password);
      toast('Welcome back!');
      onClose();
    } catch { toast('Login failed'); }
  };

  return (
    <ModalWrapper title="Sign In" onClose={onClose}>
      <input
        id="login-email"
        name="email"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
        autoComplete="email"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
      />
      <input
        id="login-password"
        name="password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
        autoComplete="current-password"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-4 outline-none"
      />
      <button
        onClick={handleSubmit}
        className="w-full py-3 bg-[var(--accent)] text-white rounded-3xl font-semibold hover:bg-[var(--accent-dark)] transition"
      >
        Sign In
      </button>
      <p className="text-center mt-3 text-xs text-[var(--text-secondary)]">
        Forgot password?{' '}
        <button className="text-[var(--accent)] underline cursor-pointer">Reset</button>
      </p>
    </ModalWrapper>
  );
}