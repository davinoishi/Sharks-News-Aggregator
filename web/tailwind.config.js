const defaultTheme = require('tailwindcss/defaultTheme')

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        // Display: mastheads, headlines, section headings. Nothing else.
        display: ['var(--font-display)', 'Oswald', ...defaultTheme.fontFamily.sans],
        // Text: the document default — body, UI, data, labels.
        sans: ['var(--font-text)', ...defaultTheme.fontFamily.sans],
      },
      // Type roles, named for the job they do. Each role carries its own
      // line-height, tracking, and weight, so a role is applied with one class
      // and cannot drift apart between screens.
      fontSize: {
        // Site identity beside the crest, on the feed.
        masthead: [
          'clamp(1.375rem, 1.05rem + 1.7vw, 2.375rem)',
          { lineHeight: '1.04', letterSpacing: '0.004em', fontWeight: '600' },
        ],
        // Site identity in the compact sub-page header lockup.
        wordmark: ['1.375rem', { lineHeight: '1.1', letterSpacing: '0.01em', fontWeight: '600' }],
        // Page h1 on a sub-page.
        title: [
          'clamp(1.5rem, 1.3rem + 0.9vw, 1.9rem)',
          { lineHeight: '1.12', letterSpacing: '0.005em', fontWeight: '600' },
        ],
        // The workhorse: a cluster headline in the feed.
        headline: [
          'clamp(1.125rem, 1.06rem + 0.3vw, 1.3125rem)',
          { lineHeight: '1.26', letterSpacing: '0.01em', fontWeight: '500' },
        ],
        // Section heading inside a document.
        subhead: ['1.375rem', { lineHeight: '1.22', letterSpacing: '0.005em', fontWeight: '600' }],
        // Sub-section heading inside a document.
        subsubhead: ['1.0625rem', { lineHeight: '1.3', letterSpacing: '0.01em', fontWeight: '600' }],
        // Running prose.
        body: ['1rem', { lineHeight: '1.65' }],
        // Interactive text: buttons, inputs, form labels, list rows.
        ui: ['0.875rem', { lineHeight: '1.4', fontWeight: '500' }],
        // A group label above a set of controls or items.
        label: ['0.75rem', { lineHeight: '1.2', letterSpacing: '0.09em', fontWeight: '600' }],
        // Timestamps, counts, source names, fine print.
        meta: ['0.8125rem', { lineHeight: '1.45' }],
        // Taxonomy chips — event type and tags.
        chip: ['0.75rem', { lineHeight: '1.1', letterSpacing: '0.045em', fontWeight: '600' }],
      },
      // Semantic colour roles. Components name the job ("surface", "action",
      // "text-muted"), never a hue — so the dark theme is a remap of these
      // roles in globals.css rather than a second set of classes.
      colors: {
        canvas: 'var(--canvas)',
        surface: 'var(--surface)',
        'surface-sunken': 'var(--surface-sunken)',

        content: 'var(--text)',
        'content-secondary': 'var(--text-secondary)',
        'content-muted': 'var(--text-muted)',

        action: 'var(--action)',
        'action-hover': 'var(--action-hover)',
        'action-quiet': 'var(--action-quiet)',
        'on-action': 'var(--on-action)',
        focus: 'var(--focus)',

        edge: 'var(--border)',
        'edge-strong': 'var(--border-strong)',

        control: 'var(--control-bg)',
        'control-fg': 'var(--control-fg)',
        'control-edge': 'var(--control-edge)',
        'control-hover': 'var(--control-hover)',

        'chip-speculation': 'var(--chip-speculation-bg)',
        'chip-speculation-fg': 'var(--chip-speculation-fg)',
        'chip-status': 'var(--chip-status-bg)',
        'chip-status-fg': 'var(--chip-status-fg)',
        'chip-confirmed': 'var(--chip-confirmed-bg)',
        'chip-confirmed-fg': 'var(--chip-confirmed-fg)',
        'chip-routine': 'var(--chip-routine-bg)',
        'chip-routine-fg': 'var(--chip-routine-fg)',
        'chip-routine-edge': 'var(--chip-routine-border)',

        trending: 'var(--trending-bg)',
        'trending-fg': 'var(--trending-fg)',

        critical: 'var(--critical-bg)',
        'critical-fg': 'var(--critical-fg)',
        'critical-edge': 'var(--critical-border)',
        caution: 'var(--caution-bg)',
        'caution-fg': 'var(--caution-fg)',
        'caution-edge': 'var(--caution-border)',
        positive: 'var(--positive-bg)',
        'positive-fg': 'var(--positive-fg)',
        'positive-edge': 'var(--positive-border)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
      },
    },
  },
  plugins: [],
}
