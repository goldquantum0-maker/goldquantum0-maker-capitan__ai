import React, { useState } from 'react';
import ModalWrapper from './ModalWrapper';
import { useAuth } from '../../context/AuthContext';

export default function SignupModal({ onClose, toast }) {
  const { signup } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');

  const handleSubmit = async () => {
    if (!email || !password) { toast('Fill all fields'); return; }
    try {
      await signup(email, password, name);
      toast('Account created! Activate wallet to get 2,000 CLOSE.');
      onClose();
    } catch { toast('Signup failed'); }
  };

  return (
    <ModalWrapper title="Create OS Wallet" onClose={onClose}>
      <input
        id="signup-email"
        name="email"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
        autoComplete="email"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
      />
      <input
        id="signup-password"
        name="password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password (min 6)"
        autoComplete="new-password"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
      />
      <input
        id="signup-name"
        name="name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Name (optional)"
        autoComplete="name"
        className="w-full p-3 border border-[var(--glass-border)] rounded-2xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-4 outline-none"
      />
      <button
        onClick={handleSubmit}
        className="w-full py-3 bg-[var(--accent)] text-white rounded-3xl font-semibold hover:bg-[var(--accent-dark)] transition"
      >
        Create Account
      </button>
      <p className="text-center mt-3 text-xs text-[var(--text-secondary)]">
        Already have an account?{' '}
        <button
          onClick={() => { onClose(); window.dispatchEvent(new CustomEvent('open-login-modal')); }}
          className="text-[var(--accent)] underline cursor-pointer"
        >
          Sign in
        </button>
      </p>
    </ModalWrapper>
  );
}