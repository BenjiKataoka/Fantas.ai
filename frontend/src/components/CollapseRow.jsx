import { useState, useEffect } from 'react'

// Expansion row that animates open (down) AND closed (up). Stays mounted through the
// close transition, then unmounts once the collapse finishes.
export default function CollapseRow({ open, colSpan, children }) {
  const [render, setRender] = useState(open)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (open) {
      setRender(true)
      // Two rAFs so the browser paints the 0fr state before we flip to 1fr, otherwise
      // it mounts already-open and the transition never runs.
      const id = requestAnimationFrame(() => requestAnimationFrame(() => setExpanded(true)))
      return () => cancelAnimationFrame(id)
    }
    setExpanded(false)  // triggers the collapse; unmount happens on transitionend
  }, [open])

  if (!render) return null
  return (
    <tr>
      <td colSpan={colSpan} className="p-0 bg-ink/30 border-l-2 border-brand">
        <div
          className="collapse-row"
          style={{ gridTemplateRows: expanded ? '1fr' : '0fr', opacity: expanded ? 1 : 0 }}
          onTransitionEnd={(e) => { if (!open && e.propertyName === 'grid-template-rows') setRender(false) }}
        >
          <div>{children}</div>
        </div>
      </td>
    </tr>
  )
}
