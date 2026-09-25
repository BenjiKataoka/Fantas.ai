// Imported only in demo mode, so the snapshot never ships in the real app's bundle.
import snapshot from './snapshot.json'
import { anchorClock, buildTable, makeAdapter } from './demoAdapter'

export function installDemo(api) {
  anchorClock(Date.parse(snapshot.recorded_at))
  api.defaults.adapter = makeAdapter(buildTable(snapshot.entries))
}
