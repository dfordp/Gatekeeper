'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { apiClient } from '@/lib/api-client';
import DashboardLayout from '@/components/dashboard/DashboardLayout';

interface ChatSession {
  session_id: string;
  user: string;
  company: string;
  telegram_chat_id: string;
  is_active: boolean;
  created_at: string;
  last_message_at: string;
}

export default function ChatManagementPage() {
  const { user, loading } = useAuth();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [formData, setFormData] = useState({
    user_id: '',
    telegram_chat_id: ''
  });
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [users, setUsers] = useState<any[]>([]);

  useEffect(() => {   
    
    loadSessions();
    loadUsers();
  }, [user]);

  const loadSessions = async () => {
    try {
      const response = await apiClient.get('/api/chat/sessions');
      setSessions(response.data.sessions);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  };

  const loadUsers = async () => {
    try {
      const response = await apiClient.get('/api/users');
      setUsers(response.data.users || []);
    } catch (error) {
      console.error('Failed to load users:', error);
    }
  };

  const handleCreateSession = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const params = new URLSearchParams({
        user_id: formData.user_id,
        telegram_chat_id: formData.telegram_chat_id
      });
      
      const response = await apiClient.post(`/api/chat/init?${params.toString()}`);

      setMessage(`✓ ${response.data.message}`);
      setFormData({ user_id: '', telegram_chat_id: '' });
      setShowCreateForm(false);
      loadSessions();
    } catch (error: any) {
      setMessage(`❌ ${error.response?.data?.detail || 'Failed to create session'}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (!confirm('Delete this chat session? This action cannot be undone.')) return;
  
    try {
      await apiClient.delete(`/api/chat/sessions/${sessionId}`);
      setMessage('✓ Session deleted');
      loadSessions();
    } catch (error: any) {
      setMessage(`❌ ${error.response?.data?.detail || 'Failed to delete session'}`);
    }
  };

  if (loading) return <div>Loading...</div>;

  return (
    <DashboardLayout>
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">Chat Management</h1>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
        >
          {showCreateForm ? 'Cancel' : '+ Create Session'}
        </button>
      </div>

      {/* Create Session Form */}
      {showCreateForm && (
        <form onSubmit={handleCreateSession} className="bg-white p-6 rounded-lg shadow space-y-4">
          <h2 className="text-xl font-bold">Create Chat Session</h2>

          <div>
            <label className="block text-sm font-medium mb-2">Select User</label>
            <select
              value={formData.user_id}
              onChange={(e) => setFormData({ ...formData, user_id: e.target.value })}
              className="w-full px-4 py-2 border rounded"
              required
            >
              <option value="">-- Choose a user --</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.email} ({u.name})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Telegram Chat ID</label>
            <p className="text-xs text-gray-600 mb-2">
              User sends <code className="bg-gray-100 px-2 py-1">/start</code> to bot to get their ID
            </p>
            <input
              type="text"
              value={formData.telegram_chat_id}
              onChange={(e) => setFormData({ ...formData, telegram_chat_id: e.target.value })}
              placeholder="e.g., 1973040145"
              className="w-full px-4 py-2 border rounded"
              required
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {isLoading ? 'Creating...' : 'Create Session'}
          </button>

          {message && (
            <div className={`p-3 rounded text-sm ${
              message.includes('✓') 
                ? 'bg-green-100 text-green-800' 
                : 'bg-red-100 text-red-800'
            }`}>
              {message}
            </div>
          )}
        </form>
      )}

      {/* Sessions Table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-100 border-b">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold">User</th>
              <th className="px-6 py-3 text-left text-sm font-semibold">Company</th>
              <th className="px-6 py-3 text-left text-sm font-semibold">Telegram ID</th>
              <th className="px-6 py-3 text-left text-sm font-semibold">Last Message</th>
              <th className="px-6 py-3 text-left text-sm font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((session) => (
              <tr key={session.session_id} className="border-b hover:bg-gray-50">
                <td className="px-6 py-4 text-sm">{session.user}</td>
                <td className="px-6 py-4 text-sm">{session.company}</td>
                <td className="px-6 py-4 text-sm font-mono text-xs">{session.telegram_chat_id}</td>
                <td className="px-6 py-4 text-sm text-gray-600">
                  {new Date(session.last_message_at).toLocaleDateString()}
                </td>
                <td className="px-6 py-4 text-sm">
                  <button
                    onClick={() => handleDeleteSession(session.session_id)}
                    className="text-red-600 hover:text-red-800"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        
        {sessions.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            No chat sessions yet
          </div>
        )}
      </div>
    </div>
    </DashboardLayout>
  );
}