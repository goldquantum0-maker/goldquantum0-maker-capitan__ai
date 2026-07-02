import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { apiCall } from '../utils/api';
import { Plus, Pin, Trash2, Edit3, FileText, Loader2, AlertCircle } from 'lucide-react';

export default function PortfolioPage({ toast }) {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [showForm, setShowForm] = useState(false);

  // Form fields
  const [formName, setFormName] = useState('');
  const [formContent, setFormContent] = useState('');
  const [formFolder, setFormFolder] = useState('General');
  const [formTags, setFormTags] = useState('');

  const fetchItems = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiCall('/api/portfolio');
      setItems(data.items || []);
    } catch (err) {
      setError(err.message || 'Failed to load portfolio');
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // Reset form
  const resetForm = () => {
    setFormName('');
    setFormContent('');
    setFormFolder('General');
    setFormTags('');
    setEditingId(null);
    setShowForm(false);
  };

  // Edit existing item
  const startEdit = (item) => {
    setFormName(item.name || '');
    setFormContent(item.content || '');
    setFormFolder(item.folder || 'General');
    setFormTags((item.tags || []).join(', '));
    setEditingId(item.id);
    setShowForm(true);
  };

  // Save (create or update)
  const handleSave = async () => {
    if (!formName.trim() || !formContent.trim()) {
      toast('Title and content are required');
      return;
    }
    const payload = {
      name: formName.trim(),
      content: formContent.trim(),
      folder: formFolder || 'General',
      tags: formTags.split(',').map(t => t.trim()).filter(Boolean),
      attachments: [],
      chat_id: null,
    };

    try {
      if (editingId) {
        await apiCall(`/api/portfolio/${editingId}`, { method: 'PUT', body: JSON.stringify(payload) });
        toast('Note updated');
      } else {
        await apiCall('/api/portfolio', { method: 'POST', body: JSON.stringify(payload) });
        toast('Note created');
      }
      resetForm();
      fetchItems();
    } catch (err) {
      toast('Save failed: ' + err.message);
    }
  };

  // Delete item
  const handleDelete = async (id) => {
    if (!confirm('Delete this note?')) return;
    try {
      await apiCall(`/api/portfolio/${id}`, { method: 'DELETE' });
      toast('Note deleted');
      fetchItems();
    } catch (err) {
      toast('Delete failed');
    }
  };

  // Toggle pin
  const handlePin = async (id, currentPinned) => {
    try {
      // Find the item to update
      const item = items.find(i => i.id === id);
      if (!item) return;
      const updated = { ...item, pinned: !currentPinned };
      await apiCall(`/api/portfolio/${id}`, { method: 'PUT', body: JSON.stringify(updated) });
      toast(currentPinned ? 'Unpinned' : 'Pinned');
      fetchItems();
    } catch (err) {
      toast('Pin toggle failed');
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
        <button onClick={fetchItems} className="text-[var(--accent)] underline text-sm">Retry</button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] p-4 md:p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Portfolio</h1>
        <button
          onClick={() => { resetForm(); setShowForm(true); }}
          className="flex items-center gap-2 px-4 py-2.5 bg-[var(--accent)] text-white rounded-2xl font-semibold text-sm hover:bg-[var(--accent-dark)] transition"
        >
          <Plus size={16} />
          New Note
        </button>
      </div>

      {/* Create/Edit Form */}
      {showForm && (
        <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-6 mb-8 backdrop-blur-xl">
          <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
            {editingId ? 'Edit Note' : 'New Note'}
          </h2>
          <input
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder="Title"
            className="w-full p-3 border border-[var(--glass-border)] rounded-xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none"
          />
          <textarea
            value={formContent}
            onChange={(e) => setFormContent(e.target.value)}
            placeholder="Content"
            rows={6}
            className="w-full p-3 border border-[var(--glass-border)] rounded-xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none resize-y"
          />
          <div className="grid grid-cols-2 gap-3 mb-4">
            <input
              value={formFolder}
              onChange={(e) => setFormFolder(e.target.value)}
              placeholder="Folder"
              className="p-3 border border-[var(--glass-border)] rounded-xl bg-[var(--bg-secondary)] text-[var(--text-primary)] outline-none"
            />
            <input
              value={formTags}
              onChange={(e) => setFormTags(e.target.value)}
              placeholder="Tags (comma separated)"
              className="p-3 border border-[var(--glass-border)] rounded-xl bg-[var(--bg-secondary)] text-[var(--text-primary)] outline-none"
            />
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleSave}
              className="flex-1 py-3 bg-[var(--accent)] text-white rounded-2xl font-semibold hover:bg-[var(--accent-dark)] transition"
            >
              {editingId ? 'Update' : 'Save'}
            </button>
            <button
              onClick={resetForm}
              className="flex-1 py-3 border border-[var(--glass-border)] text-[var(--text-primary)] rounded-2xl font-semibold hover:bg-[var(--bg-tertiary)] transition"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Notes List */}
      {items.length === 0 ? (
        <div className="text-center py-16">
          <FileText size={48} className="mx-auto text-[var(--text-tertiary)] mb-4" />
          <p className="text-[var(--text-secondary)]">No notes yet. Create your first one!</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map(item => (
            <div
              key={item.id}
              className={`bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-5 backdrop-blur-xl hover:border-[var(--accent)] transition group ${
                item.pinned ? 'ring-2 ring-[var(--accent)]' : ''
              }`}
            >
              <div className="flex justify-between items-start mb-2">
                <div>
                  <h3 className="font-semibold text-[var(--text-primary)] text-lg">{item.name}</h3>
                  {item.tags?.length > 0 && (
                    <div className="flex gap-1 mt-1">
                      {item.tags.map(tag => (
                        <span key={tag} className="text-[10px] bg-[var(--bg-tertiary)] text-[var(--text-secondary)] px-2 py-0.5 rounded-full">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition">
                  <button
                    onClick={() => handlePin(item.id, item.pinned)}
                    className={`p-1.5 rounded-lg ${item.pinned ? 'text-[var(--accent)]' : 'text-[var(--text-tertiary)]'} hover:bg-[var(--bg-tertiary)]`}
                    title={item.pinned ? 'Unpin' : 'Pin'}
                  >
                    <Pin size={14} />
                  </button>
                  <button
                    onClick={() => startEdit(item)}
                    className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)]"
                    title="Edit"
                  >
                    <Edit3 size={14} />
                  </button>
                  <button
                    onClick={() => handleDelete(item.id)}
                    className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)] hover:text-rose-400"
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <p className="text-sm text-[var(--text-secondary)] line-clamp-3">
                {item.content}
              </p>
              <div className="mt-3 text-xs text-[var(--text-tertiary)]">
                {item.folder && <span className="mr-3">📁 {item.folder}</span>}
                {item.created_at && <span>{new Date(item.created_at).toLocaleDateString()}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}