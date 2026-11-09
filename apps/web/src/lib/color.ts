/** WCAG goreli parlaklik (0..1); gecersiz hex icin null. */
export function relativeLuminance(hex: string): number | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return null
  const n = parseInt(m[1], 16)
  const lin = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
}

/** Renkli zemin (etiket, board sekmesi) uzerinde okunur yazi rengi: koyu murekkep ya da beyaz. */
export function readableTextOn(hex: string): string {
  const l = relativeLuminance(hex)
  if (l == null) return '#ffffff'
  // Beyaz ile kontrast (1.05/(l+.05)) koyu murekkep (#0f1422, l~0.007) ile kontrastindan buyukse beyaz
  const white = 1.05 / (l + 0.05)
  const ink = (l + 0.05) / (0.0075 + 0.05)
  return white >= ink ? '#ffffff' : '#0f1422'
}
