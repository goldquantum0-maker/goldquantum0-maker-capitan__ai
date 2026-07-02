import React from 'react';
import { X } from 'lucide-react';

export default function NotifPanel({ open, onClose }) {
  return (
    <div
      className={`fixed top-0 h-full w-[320px] bg-[var(--glass-bg)] border-l border-[var(--glass-border)] z-[200] backdrop-blur-xl transition-all duration-300 overflow-y-auto p-4 ${
        open ? 'right-0' : '-right-[360px]'
      }`}
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">Notifications</h3>
        <button onClick={onClose} className="text-[var(--text-tertiary)]">
          <X size={18} />
        </button>
      </div>
      <div className="text-sm text-[var(--text-secondary)]">No new notifications</div>
    </div>
  );
}