// Categorical palette used across donut/pie/bar charts. Kept distinct from
// semantic P&L colors (green/red) so allocation charts don't imply good/bad.
export const CATEGORICAL_COLORS = [
  '#2b8cff', // brand blue
  '#22c55e', // green
  '#f59e0b', // amber
  '#a78bfa', // violet
  '#f87171', // red
  '#22d3ee', // cyan
  '#fb923c', // orange
  '#e879f9', // fuchsia
  '#94a3b8', // slate
  '#4ade80', // light green
  '#818cf8', // indigo
  '#facc15', // yellow
];

export function colorForIndex(i: number): string {
  return CATEGORICAL_COLORS[i % CATEGORICAL_COLORS.length];
}
