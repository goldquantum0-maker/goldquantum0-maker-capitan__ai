import React, { useState, useEffect, useCallback } from 'react';
import { apiCall } from '../utils/api';
import { Loader2, AlertCircle, Trophy, Flame, Zap } from 'lucide-react';

const tabs = [
  { key: 'staked', label: 'Staked', icon: Trophy },
  { key: 'burned', label: 'Burned', icon: Flame },
  { key: 'streak', label: 'Streak', icon: Zap },
];

export default function LeaderboardPage() {
  const [activeTab, setActiveTab] = useState('staked');
  const [leaders, setLeaders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchLeaders = useCallback(async (type) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiCall(`/api/leaderboard?type=${type}`);
      setLeaders(data.leaderboard || []);
    } catch (err) {
      setError(err.message || 'Failed to load leaderboard');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLeaders(activeTab);
  }, [activeTab, fetchLeaders]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-[var(--accent)]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] flex flex-col items-center justify-center p-6">
        <AlertCircle size={32} className="text-rose-400 mb-3" />
        <p className="text-rose-400 text-sm mb-4">{error}</p>
        <button onClick={() => fetchLeaders(activeTab)} className="text-[var(--accent)] underline text-sm">Retry</button>
      </div>
    );
  }

  const medals = ['🥇', '🥈', '🥉'];

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] p-4 md:p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Leaderboard</h1>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {tabs.map(t => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`flex items-center gap-2 px-4 py-2 rounded-2xl text-sm font-semibold transition ${
                activeTab === t.key ? 'bg-[var(--accent)] text-white' : 'bg-[var(--glass-bg)] border border-[var(--glass-border)] text-[var(--text-secondary)]'
              }`}
            >
              <Icon size={14} />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Leaderboard list */}
      {leaders.length === 0 ? (
        <div className="text-center py-12">
          <Trophy size={40} className="mx-auto text-[var(--text-tertiary)] mb-3" />
          <p className="text-[var(--text-secondary)]">No data yet. Be the first!</p>
        </div>
      ) : (
        <div className="space-y-2">
          {leaders.map((entry, index) => (
            <div
              key={entry.id || index}
              className="flex items-center justify-between bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-xl p-4 backdrop-blur-xl"
            >
              <div className="flex items-center gap-3">
                <span className="text-xl w-8 text-center">
                  {index < 3 ? medals[index] : (index + 1)}
                </span>
                <div>
                  <div className="font-semibold text-sm">{entry.name || entry.email?.split('@')[0]}</div>
                  {entry.email && <div className="text-xs text-[var(--text-tertiary)]">{entry.email}</div>}
                </div>
              </div>
              <div className="font-mono text-sm text-[var(--accent)] font-semibold">
                {typeof entry.value === 'number' ? entry.value.toLocaleString() : entry.value}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}