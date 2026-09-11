import { useState, useCallback } from 'react'
import { getRoster } from '../services/api'

export function useRoster() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lastRefresh, setLastRefresh] = useState(null)

  const fetch = useCallback(async (sleeperUsername, leagueId) => {
    setLoading(true)
    setError(null)
    try {
      const res = await getRoster(sleeperUsername, leagueId)
      setData(res.data)
      setLastRefresh(new Date())
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load roster.')
    } finally {
      setLoading(false)
    }
  }, [])

  return { data, loading, error, lastRefresh, fetch }
}
