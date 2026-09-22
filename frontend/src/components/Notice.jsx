import { Link } from 'react-router-dom'

/**
 * One treatment for every "nothing here" and "that failed" state: a plain sentence and,
 * where there's something to do about it, one action.
 *
 * tone: 'quiet' (empty state) | 'error' (something broke)
 */
export default function Notice({ title, message, tone = 'quiet', actionLabel, onAction, to }) {
  const action = actionLabel && (to
    ? <Link to={to} className="text-sm font-medium text-content underline underline-offset-2">{actionLabel}</Link>
    : <button type="button" onClick={onAction} className="text-sm font-medium text-content underline underline-offset-2">{actionLabel}</button>)
  return (
    <div role={tone === 'error' ? 'alert' : undefined} className="py-14 text-center">
      <p className={`text-sm ${tone === 'error' ? 'text-bear' : 'text-content'}`}>{title}</p>
      {message && <p className="text-sm text-subtle mt-1.5 max-w-md mx-auto">{message}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}
