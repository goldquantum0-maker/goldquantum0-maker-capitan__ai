import React from 'react';
import { X } from 'lucide-react';

export default function ModalWrapper({ children, onClose, title }) {
  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70 backdrop-blur-md animate-modal-overlay-in"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-3xl w-full max-w-[540px] max-h-[85vh] overflow-y-auto p-6 shadow-2xl backdrop-blur-xl animate-modal-scale-in">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">{title}</h2>
          <button onClick={onClose} className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}