/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        base: {
          bg: '#0b1120',
          surface: '#111a2e',
          surface2: '#16213a',
          border: '#22304d',
        },
        brand: {
          50: '#eef7ff',
          100: '#d9edff',
          200: '#bce0ff',
          300: '#8ccbff',
          400: '#55aeff',
          500: '#2b8cff',
          600: '#166ef2',
          700: '#1259d6',
          800: '#154aa8',
          900: '#173f84',
        },
        positive: {
          DEFAULT: '#22c55e',
          bg: 'rgba(34,197,94,0.12)',
        },
        negative: {
          DEFAULT: '#f87171',
          bg: 'rgba(248,113,113,0.12)',
        },
        neutral: {
          DEFAULT: '#94a3b8',
          bg: 'rgba(148,163,184,0.12)',
        },
        warn: {
          DEFAULT: '#fbbf24',
          bg: 'rgba(251,191,36,0.12)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px 0 rgba(0,0,0,0.3), 0 1px 3px 1px rgba(0,0,0,0.2)',
      },
    },
  },
  plugins: [],
}
