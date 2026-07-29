export function formatBytes(bytes: number): string {
  if (!bytes) {
    return '0 B'
  }
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`
}

export function formatNumber(value: unknown): string {
  const number = Number(value)
  if (!Number.isFinite(number)) {
    return String(value)
  }
  return Number.isInteger(number)
    ? String(number)
    : number.toFixed(2).replace(/\.?0+$/, '')
}

export function formatLanguageDistribution(distribution: Record<string, number>): string {
  return Object.entries(distribution)
    .filter(([, share]) => Number(share) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .map(([language, share]) => `${language} ${Math.round(Number(share) * 100)}%`)
    .join(', ')
}
