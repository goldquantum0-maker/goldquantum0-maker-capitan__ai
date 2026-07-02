import React from 'react';

export default function SplashScreen() {
  return (
    <div className="fixed inset-0 z-[10000] bg-gradient-to-br from-[#0a0f14] to-[#0d3b4f] flex items-center justify-center">
      <svg className="w-20 h-20 animate-splash-pulse" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="42" fill="none" stroke="#00b4d8" strokeWidth="3" style={{ filter: 'drop-shadow(0 0 12px #00b4d8)' }} />
        <circle cx="50" cy="50" r="32" fill="none" stroke="#90e0ef" strokeWidth="1.5" strokeDasharray="15 8" />
        <text x="50" y="62" textAnchor="middle" fontFamily="Inter,sans-serif" fontSize="44" fill="white" fontWeight="800">C</text>
      </svg>
    </div>
  );
}