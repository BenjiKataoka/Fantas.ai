import { useEffect, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { getAdminUsers, approveUser, revokeUser } from '../services/api'
import { TableSkeleton } from '../components/Skeletons'
import { LoadingDots } from '../components/Spinner'

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
      toast.success(approve ? 'User approved' : 'Access revoked')
      await load()
    } catch (err) {
      const msg = err.response?.data?.detail || 'Action failed.'
      setError(msg)
      toast.error(msg)
    } finally {
      setBusyId(null)
    }
  }

  if (loading) return <TableSkeleton rows={5} />

  const pending = users.filter(u => !u.is_approved)

  return (
    <div>
      <div className="flex items-baseline justify-between mb-4 pb-4 border-b border-line">
        <h1 className="text-2xl font-display font-bold text-content">Admin</h1>
        <span className="text-sm text-subtle font-mono">
          {users.length} users · {pending.length} pending
        </span>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-bear/10 border border-bear/30 rounded-lg text-bear text-sm">{error}</div>
      )}

      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full text-left">
          <thead className="bg-raised border-b border-line">
            <tr>
              {['User', 'Status', 'Joined', ''].map((h, i) => (
                <th key={i} className="px-4 py-2.5 text-xs font-medium text-subtle">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line/40">
            {users.map(u => (
              <tr key={u.id} className="hover:bg-raised/50 transition-colors">
                <td className="px-4 py-3">
                  <div className="text-sm text-content font-medium">
                    {u.username}
                    {u.is_admin && <span className="ml-2 text-xs text-brand">admin</span>}
                  </div>
                  <div className="text-xs text-subtle">{u.email}</div>
                </td>
                <td className="px-4 py-3">
                  {u.is_approved ? (
                    <span className="text-xs px-2 py-0.5 rounded bg-bull/10 text-bull border border-bull/30">Approved</span>
                  ) : (
                    <span className="text-xs px-2 py-0.5 rounded bg-warn/10 text-warn border border-warn/30">Pending</span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-subtle font-mono">
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : '-'}
                </td>
                <td className="px-4 py-3 text-right">
                  {u.is_admin ? (
                    <span className="text-xs text-faint">-</span>
                  ) : u.is_approved ? (
                    <button
                      onClick={() => act(u.id, false)}
                      disabled={busyId === u.id}
                      className="px-3 py-1 text-xs font-medium rounded-md bg-raised hover:bg-line text-subtle hover:text-content border border-line disabled:opacity-40 transition-colors"
                    >
                      {busyId === u.id ? <LoadingDots /> : 'Revoke'}
                    </button>
                  ) : (
                    <button
                      onClick={() => act(u.id, true)}
                      disabled={busyId === u.id}
                      className="px-3 py-1 text-xs font-semibold rounded-md bg-brand hover:brightness-110 text-brand-fg disabled:opacity-40 transition-all"
                    >
                      {busyId === u.id ? <LoadingDots /> : 'Approve'}
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
