import React, { useState, useEffect, useCallback } from 'react';
import { apiCall } from '../utils/api';
import { Key, Webhook, Plus, Trash2, Copy, Loader2, AlertCircle } from 'lucide-react';

export default function DeveloperPage({ toast }) {
  const [keys, setKeys] = useState([]);
  const [webhooks, setWebhooks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [showWebhookModal, setShowWebhookModal] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState('');
  const [webhookEvents, setWebhookEvents] = useState('new_message');

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [keyData, hookData] = await Promise.all([
        apiCall('/api/developer/keys'),
        apiCall('/api/developer/webhooks')
      ]);
      setKeys(keyData.keys || []);
      setWebhooks(hookData.webhooks || []);
    } catch (err) {
      setError(err.message || 'Failed to load developer data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const createKey = async () => {
    try {
      const res = await apiCall('/api/developer/keys', { method: 'POST', body: JSON.stringify({}) });
      navigator.clipboard.writeText(res.key);
      toast('API key copied to clipboard!');
      fetchAll();
    } catch (err) {
      toast('Failed to create key');
    }
  };

  const revokeKey = async (id) => {
    if (!confirm('Revoke this key?')) return;
    try {
      await apiCall(`/api/developer/keys/${id}`, { method: 'DELETE' });
      toast('Key revoked');
      fetchAll();
    } catch (err) {
      toast('Revoke failed');
    }
  };

  const createWebhook = async () => {
    if (!webhookUrl.trim()) { toast('URL required'); return; }
    try {
      await apiCall('/api/developer/webhooks', {
        method: 'POST',
        body: JSON.stringify({ url: webhookUrl, events: webhookEvents.split(',').map(e => e.trim()) })
      });
      toast('Webhook created');
      setShowWebhookModal(false);
      setWebhookUrl('');
      setWebhookEvents('new_message');
      fetchAll();
    } catch (err) {
      toast('Failed to create webhook');
    }
  };

  const deleteWebhook = async (id) => {
    if (!confirm('Delete this webhook?')) return;
    try {
      await apiCall(`/api/developer/webhooks/${id}`, { method: 'DELETE' });
      toast('Webhook deleted');
      fetchAll();
    } catch (err) {
      toast('Delete failed');
    }
  };

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
        <button onClick={fetchAll} className="text-[var(--accent)] underline text-sm">Retry</button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] p-4 md:p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-8">Developer</h1>

      {/* API Keys */}
      <section className="mb-10">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2"><Key size={18} /> API Keys</h2>
          <button onClick={createKey} className="flex items-center gap-2 px-4 py-2 bg-[var(--accent)] text-white rounded-2xl text-sm font-semibold">
            <Plus size={14} /> Generate Key
          </button>
        </div>
        {keys.length === 0 ? (
          <p className="text-[var(--text-secondary)] text-sm">No API keys yet.</p>
        ) : (
          <div className="space-y-2">
            {keys.map(k => (
              <div key={k.id} className="flex justify-between items-center bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-xl p-4 backdrop-blur-xl">
                <div>
                  <div className="font-mono text-sm">{k.prefix}••••••••</div>
                  <div className="text-xs text-[var(--text-tertiary)]">Scopes: {k.scopes || 'default'} · Last used: {k.last_used || 'never'}</div>
                </div>
                <button onClick={() => revokeKey(k.id)} className="p-2 text-rose-400 hover:bg-[var(--bg-tertiary)] rounded-lg">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Webhooks */}
      <section>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2"><Webhook size={18} /> Webhooks</h2>
          <button onClick={() => setShowWebhookModal(true)} className="flex items-center gap-2 px-4 py-2 bg-[var(--accent)] text-white rounded-2xl text-sm font-semibold">
            <Plus size={14} /> Add Webhook
          </button>
        </div>

        {showWebhookModal && (
          <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-4 mb-4 backdrop-blur-xl">
            <input value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} placeholder="https://your-webhook.url" className="w-full p-2.5 border border-[var(--glass-border)] rounded-xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-2 outline-none text-sm" />
            <input value={webhookEvents} onChange={(e) => setWebhookEvents(e.target.value)} placeholder="Events (comma separated)" className="w-full p-2.5 border border-[var(--glass-border)] rounded-xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none text-sm" />
            <div className="flex gap-2">
              <button onClick={createWebhook} className="flex-1 py-2.5 bg-[var(--accent)] text-white rounded-xl font-semibold text-sm">Save</button>
              <button onClick={() => setShowWebhookModal(false)} className="flex-1 py-2.5 border border-[var(--glass-border)] text-[var(--text-primary)] rounded-xl font-semibold text-sm">Cancel</button>
            </div>
          </div>
        )}

        {webhooks.length === 0 ? (
          <p className="text-[var(--text-secondary)] text-sm">No webhooks configured.</p>
        ) : (
          <div className="space-y-2">
            {webhooks.map(w => (
              <div key={w.id} className="flex justify-between items-center bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-xl p-4 backdrop-blur-xl">
                <div>
                  <div className="text-sm font-mono break-all">{w.url}</div>
                  <div className="text-xs text-[var(--text-tertiary)]">Events: {(w.events || []).join(', ')}</div>
                </div>
                <button onClick={() => deleteWebhook(w.id)} className="p-2 text-rose-400 hover:bg-[var(--bg-tertiary)] rounded-lg">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}