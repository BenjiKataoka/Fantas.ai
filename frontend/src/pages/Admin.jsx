import { useEffect, useState, useCallback } from 'react'
import { getAdminUsers, approveUser, revokeUser } from '../services/api'
import Spinner from '../components/Spinner'

export default function Admin() {
  const [users, setUsers]     = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [busyId, setBusyId]   = useState(null)

  const load = useCallback(async () => {
    try {
      const res = await getAdminUsers()
      setUsers(res.data.users || [])
      setError(null)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load users.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const act = async (userId, approve) => {
    setBusyId(userId)
    try {
      await (approve ? approveUser(userId) : revokeUser(userId))
      await load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Action failed.')
    } finally {
      setBusyId(null)
    }
  }

  if (loading) return <Spinner label="Loading users…" />

  const pending = users.filter(u => !u.is_approved)

  return (
    <div>
      <div className="flex items-baseline justify-between mb-4 pb-4 border-b border-gray-800">
        <h1 className="text-2xl font-bold">Admin</h1>
        <span className="text-sm text-gray-500">
          {users.length} users · {pending.length} pending
        </span>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-400 text-sm">{error}</div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-left">
          <thead className="bg-gray-900 border-b border-gray-800">
            <tr>
              {['User', 'Status', 'Joined', ''].map((h, i) => (
                <th key={i} className="px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-gray-950 divide-y divide-gray-800/40">
            {users.map(u => (
              <tr key={u.id} className="hover:bg-gray-800/30 transition-colors">
                <td className="px-4 py-3">
                  <div className="text-sm text-white font-medium">
                    {u.username}
                    {u.is_admin && <span className="ml-2 text-xs text-blue-400">admin</span>}
                  </div>
                  <div className="text-xs text-gray-500">{u.email}</div>
                </td>
                <td className="px-4 py-3">
                  {u.is_approved ? (
                    <span className="text-xs px-2 py-0.5 rounded bg-green-900/40 text-green-400 border border-green-800/50">Approved</span>
                  ) : (
                    <span className="text-xs px-2 py-0.5 rounded bg-yellow-900/40 text-yellow-400 border border-yellow-800/50">Pending</span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                </td>
                <td className="px-4 py-3 text-right">
                  {u.is_admin ? (
                    <span className="text-xs text-gray-600">—</span>
                  ) : u.is_approved ? (
                    <button
                      onClick={() => act(u.id, false)}
                      disabled={busyId === u.id}
                      className="px-3 py-1 text-xs font-medium rounded-md bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 disabled:opacity-40"
                    >
                      {busyId === u.id ? '…' : 'Revoke'}
                    </button>
                  ) : (
                    <button
                      onClick={() => act(u.id, true)}
                      disabled={busyId === u.id}
                      className="px-3 py-1 text-xs font-semibold rounded-md bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40"
                    >
                      {busyId === u.id ? '…' : 'Approve'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
