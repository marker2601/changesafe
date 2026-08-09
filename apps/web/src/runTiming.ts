export function formatElapsed(milliseconds: number): string {
  const bounded = Math.max(0, milliseconds);
  if (bounded < 1_000) return `${(bounded / 1_000).toFixed(2)} seconds`;
  if (bounded < 10_000) return `${(bounded / 1_000).toFixed(1)} seconds`;
  return `${Math.round(bounded / 1_000)} seconds`;
}
