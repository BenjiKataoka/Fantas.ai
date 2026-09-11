const STYLES = {
  HIGH:   'text-green-500',
  MEDIUM: 'text-yellow-500',
  LOW:    'text-red-500',
}

export default function ConfidenceBadge({ flag }) {
  if (!flag) return null
  return (
    <span className={`text-xs font-medium ${STYLES[flag] || 'text-gray-500'}`}>
      {flag}
    </span>
  )
}
