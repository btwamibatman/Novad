import {
  formatBytes,
  formatLanguageDistribution,
  formatNumber,
} from '@/utils/format'

describe('format utilities', () => {
  it('formats byte counts', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
  })

  it('formats numeric values without redundant zeros', () => {
    expect(formatNumber(2)).toBe('2')
    expect(formatNumber(2.5)).toBe('2.5')
  })

  it('sorts language distribution by share', () => {
    expect(formatLanguageDistribution({ ru: 0.25, en: 0.75 })).toBe(
      'en 75%, ru 25%',
    )
  })
})
