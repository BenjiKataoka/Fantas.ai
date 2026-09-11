import { useState, useEffect } from 'react'
import { getSettings, updateSettings } from '../services/api'

export function useSettings() {
  const [weights, setWeights] = useState({
    weight_sleeper: 0.35,
    weight_espn: 0.30,
    weight_fp: 0.35,
  })
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)

  useEffect(() => {
    getSettings()
      .then(res => setWeights(res.data))
      .catch(() => {}) // fall back to defaults silently
      .finally(() => setLoaded(true))
  }, [])

  const save = async (newWeights) => {
    setSaving(true)
    setSaveError(null)
    try {
      const res = await updateSettings(newWeights)
      setWeights(res.data)
    } catch (err) {
      setSaveError(err.response?.data?.detail || 'Failed to save weights.')
    } finally {
      setSaving(false)
    }
  }

  return { weights, setWeights, loaded, saving, saveError, save }
}
