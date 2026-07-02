import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiCall } from '../utils/api';
import { Loader2, AlertCircle, Search, Edit3, Trash2 } from 'lucide-react';
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);

export default function FounderDashboard({ toast }) {
  const [dashboard, setDashboard] = useState(null);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const chartRefs = useRef({ userChart: null, burnChart: null });

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dash, usr] = await Promise.all([
        apiCall('/api/admin/dashboard'),
        apiCall(`/api/admin/users?search=${encodeURIComponent(search)}`)
      ]);
      setDashboard(dash);
      setUsers(usr.users || []);
    } catch (err) {
      setError(err.message || 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Charts
  useEffect(() => {
    if (!dashboard?.dates) return;
    const userCanvas = document.getElementById('userChart');
    const burnCanvas = document.getElementById('burnChart');
    if (userCanvas && chartRefs.current.userChart) {
      chartRefs.current.userChart.destroy();
    }
    if (burnCanvas && chartRefs.current.burnChart) {
      chartRefs.current.burnChart.destroy();
    }
    if (userCanvas) {
      chartRefs.current.userChart = new Chart(userCanvas, {
        type: 'line',
        data: {
          labels: dashboard.dates,
          datasets: [{ label: 'New Users', data: dashboard.users, borderColor: '#00b4d8', tension: 0.3 }]
        }
      });
    }
    if (burnCanvas) {
      chartRefs.current.burnChart = new Chart(burnCanvas, {
        type: 'line',
        data: {
          labels: dashboard.dates,
          datasets: [{ label: 'CLOSE Burned', data: dashboard.burns, borderColor: '#f43f5e', tension: 0.3 }]
        }
      });
    }
    return () => {
      if (chartRefs.current.userChart) chartRefs.current.userChart.destroy();
      if (chartRefs.current.burnChart) chartRefs.current.burnChart.destroy();
    };
  }, [dashboard]);

  const handleAdjust = async (userId) => {
    const amount = prompt('Amount to add (can be negative):', '0');
    if (amount === null) return;
    try {
      await apiCall(`/api/admin/user/${userId}/close`, {
        method: 'POST',
        body: JSON.stringify({ amount: parseInt(amount) })
      });
      toast('Balance adjusted');
      fetchData();
    } catch (err) {
      toast('Adjust failed');
    }
  };

  const handleDelete = async (userId) => {
    if (!confirm('Delete this user permanently?')) return;
    try {
      await apiCall(`/api/admin/user/${userId}`, { method: 'DELETE' });
      toast('User deleted');
      fetchData();
    } catch (err) {
      toast('Delete failed');
    }
  };

  if (loading && !dashboard) {
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
        <button onClick={fetchData} className="text-[var(--accent)] underline text-sm">Retry</button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] p-4 md:p-8 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-8">Dashboard</h1>

      {/* KPI cards */}
      {dashboard && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
          {[
            { label: 'Total Users', value: dashboard.total_users },
            { label: 'Active Today', value: dashboard.active_today },
            { label: 'CLOSE Circulating', value: (dashboard.close_circulating || 0).toLocaleString() },
            { label: 'CLOSE Staked', value: (dashboard.close_staked || 0).toLocaleString() },
            { label: 'CLOSE Burned', value: (dashboard.close_burned || 0).toLocaleString() },
            { label: 'Revenue (USD)', value: '$' + (dashboard.total_revenue_usd || 0).toFixed(2) },
          ].map(card => (
            <div key={card.label} className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-4 backdrop-blur-xl">
              <div className="text-xs text-[var(--text-secondary)] mb-1">{card.label}</div>
              <div className="text-lg font-bold text-[var(--text-primary)]">{card.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Charts */}
      {dashboard?.dates && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-4 backdrop-blur-xl">
            <h3 className="font-semibold mb-3">30‑Day New Users</h3>
            <canvas id="userChart" width="400" height="200"></canvas>
          </div>
          <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-4 backdrop-blur-xl">
            <h3 className="font-semibold mb-3">30‑Day CLOSE Burned</h3>
            <canvas id="burnChart" width="400" height="200"></canvas>
          </div>
        </div>
      )}

      {/* User search & table */}
      <div className="mb-4">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-3.5 text-[var(--text-tertiary)]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search users..."
            className="w-full pl-10 p-3 border border-[var(--glass-border)] rounded-xl bg-[var(--bg-secondary)] text-[var(--text-primary)] outline-none text-sm"
          />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-[var(--text-secondary)]">
              <th className="p-2">Email</th>
              <th className="p-2">Name</th>
              <th className="p-2">CLOSE</th>
              <th className="p-2">Staked</th>
              <th className="p-2">Tier</th>
              <th className="p-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-4 text-center text-[var(--text-tertiary)]">No users found</td>
              </tr>
            ) : (
              users.map(u => (
                <tr key={u.id} className="border-b border-[var(--border)] hover:bg-[var(--bg-secondary)] transition">
                  <td className="p-2">{u.email}</td>
                  <td className="p-2">{u.name || '-'}</td>
                  <td className="p-2 font-mono">{u.close_balance}</td>
                  <td className="p-2 font-mono">{u.close_staked}</td>
                  <td className="p-2 uppercase text-xs font-semibold">{u.stake_tier}</td>
                  <td className="p-2 flex gap-1">
                    <button onClick={() => handleAdjust(u.id)} className="p-1.5 text-[var(--accent)] hover:bg-[var(--bg-tertiary)] rounded-lg"><Edit3 size={14} /></button>
                    <button onClick={() => handleDelete(u.id)} className="p-1.5 text-rose-400 hover:bg-[var(--bg-tertiary)] rounded-lg"><Trash2 size={14} /></button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}