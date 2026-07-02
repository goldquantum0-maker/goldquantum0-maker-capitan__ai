import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { useWallet } from '../context/WalletContext';
import { apiCall } from '../utils/api';
import { Plus, LogIn, ArrowLeft, Send, Loader2, AlertCircle, Users, Hash } from 'lucide-react';

export default function WorkspacePage({ toast }) {
  const { user } = useAuth();
  const { sessionPassword } = useWallet();
  const [rooms, setRooms] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeRoom, setActiveRoom] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMsg, setNewMsg] = useState('');
  const [creating, setCreating] = useState(false);
  const [joining, setJoining] = useState(false);
  const [formName, setFormName] = useState('');
  const [formCode, setFormCode] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [joinPassword, setJoinPassword] = useState('');

  const fetchRooms = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiCall('/api/hub/rooms');
      setRooms(data.rooms || []);
    } catch (err) {
      setError(err.message || 'Failed to load rooms');
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => { fetchRooms(); }, [fetchRooms]);

  const loadRoomMessages = async (roomCode) => {
    try {
      const data = await apiCall(`/api/hub/rooms/${roomCode}/messages`);
      setMessages(data.messages || []);
    } catch (err) {
      toast('Failed to load messages');
    }
  };

  const enterRoom = (room) => {
    setActiveRoom(room);
    loadRoomMessages(room.room_code);
  };

  const leaveRoom = () => {
    setActiveRoom(null);
    setMessages([]);
  };

  const handleCreate = async () => {
    if (!formName.trim()) { toast('Room name required'); return; }
    setCreating(true);
    try {
      await apiCall('/api/hub/rooms', {
        method: 'POST',
        body: JSON.stringify({ name: formName, room_code: formCode || undefined })
      });
      toast('Room created');
      setFormName('');
      setFormCode('');
      fetchRooms();
    } catch (err) {
      toast('Creation failed: ' + err.message);
    } finally {
      setCreating(false);
    }
  };

  const handleJoin = async () => {
    if (!joinCode.trim()) { toast('Room code required'); return; }
    if (!sessionPassword) { toast('Unlock your wallet first'); return; }
    setJoining(true);
    try {
      const res = await apiCall('/api/hub/rooms/join', {
        method: 'POST',
        body: JSON.stringify({ room_code: joinCode.toUpperCase(), password: sessionPassword })
      });
      toast('Joined! Burn TX: ' + (res.burn_tx?.slice(0, 10) + '...' || 'success'));
      setJoinCode('');
      setJoinPassword('');
      fetchRooms();
    } catch (err) {
      toast('Join failed: ' + err.message);
    } finally {
      setJoining(false);
    }
  };

  const handleSend = async () => {
    if (!newMsg.trim()) return;
    try {
      await apiCall(`/api/hub/rooms/${activeRoom.room_code}/messages`, {
        method: 'POST',
        body: JSON.stringify({ message: newMsg.trim() })
      });
      setNewMsg('');
      loadRoomMessages(activeRoom.room_code);
    } catch (err) {
      toast('Send failed');
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
        <button onClick={fetchRooms} className="text-[var(--accent)] underline text-sm">Retry</button>
      </div>
    );
  }

  // Room chat view
  if (activeRoom) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] flex flex-col p-4">
        <div className="flex items-center gap-3 mb-4">
          <button onClick={leaveRoom} className="p-2 rounded-full bg-[var(--glass-bg)] border border-[var(--glass-border)] text-[var(--text-secondary)]">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h2 className="text-lg font-semibold">{activeRoom.name}</h2>
            <div className="text-xs text-[var(--text-tertiary)] flex items-center gap-2">
              <Hash size={12} /> {activeRoom.room_code} · <Users size={12} /> {activeRoom.member_count || 1}
            </div>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto bg-[var(--bg-secondary)] rounded-2xl p-4 mb-4 border border-[var(--border)]">
          {messages.map((m, i) => (
            <div key={i} className="mb-2">
              <span className="font-semibold text-sm text-[var(--accent)]">{m.author}:</span>
              <span className="text-sm text-[var(--text-primary)] ml-2">{m.message}</span>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={newMsg}
            onChange={(e) => setNewMsg(e.target.value)}
            placeholder="Type a message..."
            className="flex-1 p-3 rounded-2xl border border-[var(--glass-border)] bg-[var(--bg-secondary)] text-[var(--text-primary)] outline-none"
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          />
          <button onClick={handleSend} className="p-3 bg-[var(--accent)] text-white rounded-2xl">
            <Send size={18} />
          </button>
        </div>
      </div>
    );
  }

  // Rooms list
  return (
    <div className="min-h-screen bg-[var(--bg-primary)] p-4 md:p-8 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Work Areas</h1>

      {/* Create & Join */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-4 backdrop-blur-xl">
          <h3 className="font-semibold mb-3">Create Room</h3>
          <input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="Room name" className="w-full p-2.5 border border-[var(--glass-border)] rounded-xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-2 outline-none text-sm" />
          <input value={formCode} onChange={(e) => setFormCode(e.target.value)} placeholder="Optional code" className="w-full p-2.5 border border-[var(--glass-border)] rounded-xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none text-sm" />
          <button onClick={handleCreate} disabled={creating} className="w-full py-2.5 bg-[var(--accent)] text-white rounded-xl font-semibold text-sm disabled:opacity-50">
            {creating ? <Loader2 size={14} className="animate-spin mx-auto" /> : 'Create'}
          </button>
        </div>
        <div className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-2xl p-4 backdrop-blur-xl">
          <h3 className="font-semibold mb-3">Join Room</h3>
          <input value={joinCode} onChange={(e) => setJoinCode(e.target.value)} placeholder="Room code" className="w-full p-2.5 border border-[var(--glass-border)] rounded-xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-2 outline-none text-sm uppercase" />
          <input type="password" value={joinPassword} onChange={(e) => setJoinPassword(e.target.value)} placeholder="Wallet password" className="w-full p-2.5 border border-[var(--glass-border)] rounded-xl bg-[var(--bg-secondary)] text-[var(--text-primary)] mb-3 outline-none text-sm" />
          <button onClick={handleJoin} disabled={joining} className="w-full py-2.5 bg-[var(--accent)] text-white rounded-xl font-semibold text-sm disabled:opacity-50">
            {joining ? <Loader2 size={14} className="animate-spin mx-auto" /> : `Join (500 CLOSE burn)`}
          </button>
        </div>
      </div>

      {/* Rooms list */}
      {rooms.length === 0 ? (
        <div className="text-center py-12">
          <Users size={40} className="mx-auto text-[var(--text-tertiary)] mb-3" />
          <p className="text-[var(--text-secondary)]">No rooms yet. Create or join one!</p>
        </div>
      ) : (
        <div className="space-y-2">
          {rooms.map(room => (
            <div
              key={room.id}
              onClick={() => enterRoom(room)}
              className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-xl p-4 backdrop-blur-xl cursor-pointer hover:border-[var(--accent)] transition"
            >
              <div className="flex justify-between items-center">
                <span className="font-semibold">{room.name}</span>
                <span className="text-xs text-[var(--text-tertiary)]">#{room.room_code}</span>
              </div>
              <div className="text-xs text-[var(--text-secondary)] mt-1">
                Members: {room.member_count || 1}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}