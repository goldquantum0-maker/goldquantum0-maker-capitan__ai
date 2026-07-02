import React from 'react';

export default function Toast({ message }) {
  return (
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 bg-[var(--glass-bg)] text-[var(--text-primary)] px-5 py-2.5 rounded-3xl text-xs z-[1100] border border-[var(--glass-border)] backdrop-blur-xl animate-toast-in">
      {message}
    </div>
  );
}