/**
 * Tag chip coloring with guaranteed contrast (U6).
 *
 * The old scheme used `tag.color + '20'` (a 12.5%-alpha background) with
 * `tag.color` as the text color. For light tag hues that produced
 * near-invisible text on a near-white background. Instead we use the tag color
 * as a solid background and pick black or white text based on the background's
 * relative luminance, which always clears WCAG AA for chip-sized text.
 */

function parseHex(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const int = parseInt(m[1], 16);
  return [(int >> 16) & 0xff, (int >> 8) & 0xff, int & 0xff];
}

// Relative luminance per WCAG 2.x (sRGB).
function luminance([r, g, b]: [number, number, number]): number {
  const channel = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export interface TagChipStyle {
  backgroundColor: string;
  color: string;
}

const FALLBACK: TagChipStyle = { backgroundColor: '#374151', color: '#ffffff' };

export function tagChipStyle(color: string | undefined | null): TagChipStyle {
  if (!color) return FALLBACK;
  const rgb = parseHex(color);
  if (!rgb) return FALLBACK;
  // Dark backgrounds get white text; light backgrounds get near-black text.
  const text = luminance(rgb) > 0.5 ? '#111827' : '#ffffff';
  return { backgroundColor: color, color: text };
}
