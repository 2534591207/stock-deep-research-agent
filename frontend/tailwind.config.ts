import type { Config } from 'tailwindcss'

// Original dark theme tokens for the research console.
// All naming is bespoke; no external design system is referenced.
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Layered near-black surfaces (deepest → raised panels)
        ink: {
          900: '#0a0d12',
          800: '#0f131a',
          700: '#151b24',
          600: '#1c2430',
          500: '#26303d',
        },
        // Neutral text/border greys
        slate: {
          line: '#2a3441',
        },
        // Single restrained accent (cool blue) for primary actions / user bubbles
        accent: {
          DEFAULT: '#3b82f6',
          soft: '#1e3a5f',
          hover: '#2f6fe0',
        },
        // Honest-signal hues (kept muted — never alarmist)
        caution: '#d6a23e',
      },
      fontFamily: {
        sans: [
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      keyframes: {
        'fade-rise': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-dot': {
          '0%, 100%': { opacity: '0.35', transform: 'scale(0.85)' },
          '50%': { opacity: '1', transform: 'scale(1)' },
        },
      },
      animation: {
        'fade-rise': 'fade-rise 0.22s ease-out',
        'pulse-dot': 'pulse-dot 1.1s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}

export default config
