// Real NFL team colors, pulled once from ESPN's public teams endpoint (they don't change
// mid-season). A quiet identity accent on player rows, never a signal color.
export const TEAMS = {
  ARI: { name: "Cardinals", color: "#a40227", alt: "#ffffff" },
  ATL: { name: "Falcons", color: "#a71930", alt: "#000000" },
  BAL: { name: "Ravens", color: "#29126f", alt: "#000000" },
  BUF: { name: "Bills", color: "#00338d", alt: "#d50a0a" },
  CAR: { name: "Panthers", color: "#0085ca", alt: "#000000" },
  CHI: { name: "Bears", color: "#0b1c3a", alt: "#e64100" },
  CIN: { name: "Bengals", color: "#fb4f14", alt: "#000000" },
  CLE: { name: "Browns", color: "#472a08", alt: "#ff3c00" },
  DAL: { name: "Cowboys", color: "#002a5c", alt: "#b0b7bc" },
  DEN: { name: "Broncos", color: "#0a2343", alt: "#fc4c02" },
  DET: { name: "Lions", color: "#0076b6", alt: "#bbbbbb" },
  GB: { name: "Packers", color: "#204e32", alt: "#ffb612" },
  HOU: { name: "Texans", color: "#021018", alt: "#eb0028" },
  IND: { name: "Colts", color: "#003b75", alt: "#ffffff" },
  JAX: { name: "Jaguars", color: "#007487", alt: "#d7a22a" },
  KC: { name: "Chiefs", color: "#e31837", alt: "#ffb612" },
  LAC: { name: "Chargers", color: "#0080c6", alt: "#ffc20e" },
  LAR: { name: "Rams", color: "#003594", alt: "#ffd100" },
  LV: { name: "Raiders", color: "#000000", alt: "#a5acaf" },
  MIA: { name: "Dolphins", color: "#008e97", alt: "#fc4c02" },
  MIN: { name: "Vikings", color: "#4f2683", alt: "#ffc62f" },
  NE: { name: "Patriots", color: "#002a5c", alt: "#c60c30" },
  NO: { name: "Saints", color: "#d3bc8d", alt: "#000000" },
  NYG: { name: "Giants", color: "#003c7f", alt: "#c9243f" },
  NYJ: { name: "Jets", color: "#115740", alt: "#ffffff" },
  OAK: { name: "Raiders", color: "#000000", alt: "#a5acaf" },
  PHI: { name: "Eagles", color: "#06424d", alt: "#000000" },
  PIT: { name: "Steelers", color: "#000000", alt: "#ffb612" },
  SEA: { name: "Seahawks", color: "#002a5c", alt: "#69be28" },
  SF: { name: "49ers", color: "#aa0000", alt: "#b3995d" },
  TB: { name: "Buccaneers", color: "#bd1c36", alt: "#3e3a35" },
  TEN: { name: "Titans", color: "#4495d2", alt: "#001532" },
  WAS: { name: "Commanders", color: "#5a1414", alt: "#ffb612" },
}

// Perceived brightness, so a near-black team color doesn't vanish on the night theme.
function luminance(hex) {
  const n = parseInt(hex.slice(1), 16)
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255
}

/** The team's color, swapped for its alternate when the primary would disappear. */
export function teamAccent(abbr, dark) {
  const team = TEAMS[abbr]
  if (!team) return null
  const [main, alt] = [team.color, team.alt]
  if (dark && luminance(main) < 0.2) return luminance(alt) > luminance(main) ? alt : main
  if (!dark && luminance(main) > 0.85) return luminance(alt) < luminance(main) ? alt : main
  return main
}

export const teamName = (abbr) => TEAMS[abbr]?.name || abbr || ''
