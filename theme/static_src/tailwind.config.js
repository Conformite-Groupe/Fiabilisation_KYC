/**
 * This is a minimal config.
 *
 * If you need the full config, get it from here:
 * https://clicktime.symantec.com/15t5Zw7NLEgoCKzPvLpU8?h=lZAKJxPx-Wc0b2ZYsf5jb8dGq8DAZe-OLBfJrmeEEHw=&u=https://unpkg.com/browse/tailwindcss%40latest/stubs/defaultConfig.stub.js
 */

module.exports = {
  /**
   * Stylesheet generation mode.
   *
   * Set mode to "jit" if you want to generate your styles on-demand as you author your templates;
   * Set mode to "aot" if you want to generate the stylesheet in advance and purge later (aka legacy mode).
   */
  content: [
      /**
       * HTML. Paths to Django template files that will contain Tailwind CSS classes.
       */

      /*  Templates within theme app (<tailwind_app_name>/templates), e.g. base.html. */
      '../templates/**/*.html',

      /* 
       * Main templates directory of the project (BASE_DIR/templates).
       * Adjust the following line to match your project structure.
       */
      '../../templates/**/*.html',
      
      /* 
       * Templates in other django apps (BASE_DIR/<any_app_name>/templates).
       * Adjust the following line to match your project structure.
       */
      '../../**/templates/**/*.html',

      /* Python: classes Tailwind construites cote serveur (forms.py, audit_views.py, ...) */
      '../../kyc/**/*.py',
      '../../accounts/**/*.py',

      /* JS applicatif embarque dans les templates/static du projet */
      '../../templates/**/*.js',

      /**
       * JS: If you use Tailwind CSS in JavaScript, uncomment the following lines and make sure
       * patterns match your project structure.
       */
      /* JS 1: Ignore any JavaScript in node_modules folder. */
      // '!../../**/node_modules',
      /* JS 2: Process all JavaScript files in the project. */
      // '../../**/*.js',

      /**
       * Python: If you use Tailwind CSS classes in Python, uncomment the following line
       * and make sure the pattern below matches your project structure.
       */
      // '../../**/*.py'
  ],
  darkMode: false, // or 'media' or 'class'
  theme: {
      container: {
           center: true,
           },
      extend: {
           spacing: {
             '4': '1rem',
              '8': '2rem',
             '12': '3rem',
              '16': '4rem',
              '20': '5rem',
              '96': '24rem',
            },
            scrollMargin: {
              '96': '24rem',
            },
            scrollPadding: {
              '96': '24rem',
            },
            colors: {
                    'emerald-50':  '#ecfdf5',  // très clair
                    'emerald-100': '#d1fae5',
                    'emerald-200': '#a7f3d0',
                    'emerald-300': '#6ee7b7',
                    'emerald-400': '#34d399',
                    'emerald-500': '#10b981',
                    'emerald-600': '#059669',
                    'emerald-700': '#047857',
                    'emerald-800': '#065f46',
                    'emerald-900': '#064e3b',
                    'emerald-950': '#022c22',
// très foncé


                // Neutres
                    'black': '#000000',
                    'white': '#ffffff',

                    // Slate
                    'slate-50': '#f8fafc',
                    'slate-100': '#f1f5f9',
                    'slate-200': '#e2e8f0',
                    'slate-300': '#cbd5e1',
                    'slate-400': '#94a3b8',
                    'slate-500': '#64748b',
                    'slate-600': '#475569',
                    'slate-700': '#334155',
                    'slate-800': '#1e293b',
                    'slate-900': '#0f172a',
                    'slate-950': '#020617',

                    // Gray
                    'gray-50': '#f9fafb',
                    'gray-100': '#f3f4f6',
                    'gray-200': '#e5e7eb',
                    'gray-300': '#d1d5db',
                    'gray-400': '#9ca3af',
                    'gray-500': '#6b7280',
                    'gray-600': '#4b5563',
                    'gray-700': '#374151',
                    'gray-800': '#1f2937',
                    'gray-900': '#111827',
                    'gray-950': '#030712',

                    // Zinc
                    'zinc-50': '#fafafa',
                    'zinc-100': '#f4f4f5',
                    'zinc-200': '#e4e4e7',
                    'zinc-300': '#d4d4d8',
                    'zinc-400': '#a1a1aa',
                    'zinc-500': '#71717a',
                    'zinc-600': '#52525b',
                    'zinc-700': '#3f3f46',
                    'zinc-800': '#27272a',
                    'zinc-900': '#18181b',
                    'zinc-950': '#09090b',

                    // Neutral
                    'neutral-50': '#fafafa',
                    'neutral-100': '#f5f5f5',
                    'neutral-200': '#e5e5e5',
                    'neutral-300': '#d4d4d4',
                    'neutral-400': '#a3a3a3',
                    'neutral-500': '#737373',
                    'neutral-600': '#525252',
                    'neutral-700': '#404040',
                    'neutral-800': '#262626',
                    'neutral-900': '#171717',
                    'neutral-950': '#0a0a0a',

                    'cyan-50':  '#ecfeff',
                    'cyan-100': '#cffafe',
                    'cyan-200': '#a5f3fc',
                    'cyan-300': '#67e8f9',
                    'cyan-400': '#22d3ee',
                    'cyan-500': '#06b6d4',
                    'cyan-600': '#0891b2',
                    'cyan-700': '#0e7490',
                    'cyan-800': '#155e75',
                    'cyan-900': '#164e63',
                    'cyan-950': '#083344',

                    // Stone
                    'stone-50': '#fafaf9',
                    'stone-100': '#f5f5f4',
                    'stone-200': '#e7e5e4',
                    'stone-300': '#d6d3d1',
                    'stone-400': '#a8a29e',
                    'stone-500': '#78716c',
                    'stone-600': '#57534e',
                    'stone-700': '#44403c',
                    'stone-800': '#292524',
                    'stone-900': '#1c1917',
                    'stone-950': '#0c0a09',

                    // Red
                    'red-50': '#fef2f2',
                    'red-100': '#fee2e2',
                    'red-200': '#fecaca',
                    'red-300': '#fca5a5',
                    'red-400': '#f87171',
                    'red-500': '#ef4444',
                    'red-600': '#dc2626',
                    'red-700': '#b91c1c',
                    'red-800': '#991b1b',
                    'red-900': '#7f1d1d',
                    'red-950': '#450a0a',

                    // Orange
                    'orange-50': '#fff7ed',
                    'orange-100': '#ffedd5',
                    'orange-200': '#fed7aa',
                    'orange-300': '#fdba74',
                    'orange-400': '#fb923c',
                    'orange-500': '#f97316',
                    'orange-600': '#ea580c',
                    'orange-700': '#c2410c',
                    'orange-800': '#9a3412',
                    'orange-900': '#7c2d12',
                    'orange-950': '#431407',

                    // Amber
                    'amber-50': '#fffbeb',
                    'amber-100': '#fef3c7',
                    'amber-200': '#fde68a',
                    'amber-300': '#fcd34d',
                    'amber-400': '#fbbf24',
                    'amber-500': '#f59e0b',
                    'amber-600': '#d97706',
                    'amber-700': '#b45309',
                    'amber-800': '#92400e',
                    'amber-900': '#78350f',
                    'amber-950': '#451a03',

                    // Yellow
                    'yellow-50': '#fefce8',
                    'yellow-100': '#fef9c3',
                    'yellow-200': '#fef08a',
                    'yellow-300': '#fde047',
                    'yellow-400': '#facc15',
                    'yellow-500': '#eab308',
                    'yellow-600': '#ca8a04',
                    'yellow-700': '#a16207',
                    'yellow-800': '#854d0e',
                    'yellow-900': '#713f12',
                    'yellow-950': '#422006',

                    // Lime
                    'lime-50': '#f7fee7',
                    'lime-100': '#ecfccb',
                    'lime-200': '#d9f99d',
                    'lime-300': '#bef264',
                    'lime-400': '#a3e635',
                    'lime-500': '#84cc16',
                    'lime-600': '#65a30d',
                    'lime-700': '#4d7c0f',
                    'lime-800': '#3f6212',
                    'lime-900': '#365314',
                    'lime-950': '#1a2e05',

                    // Green (emerald alias)
                    'green-50': '#f0fdf4',
                    'green-100': '#dcfce7',
                    'green-200': '#bbf7d0',
                    'green-300': '#86efac',
                    'green-400': '#4ade80',
                    'green-500': '#22c55e',
                    'green-600': '#16a34a',
                    'green-700': '#15803d',
                    'green-800': '#166534',
                    'green-900': '#14532d',
                    'green-950': '#052e16',

                    // Blue
                    'blue-50': '#eff6ff',
                    'blue-100': '#dbeafe',
                    'blue-200': '#bfdbfe',
                    'blue-300': '#93c5fd',
                    'blue-400': '#60a5fa',
                    'blue-500': '#3b82f6',
                    'blue-600': '#2563eb',
                    'blue-700': '#1d4ed8',
                    'blue-800': '#1e40af',
                    'blue-900': '#1e3a8a',
                    'blue-950': '#172554',

                    // Indigo
                    'indigo-50': '#eef2ff',
                    'indigo-100': '#e0e7ff',
                    'indigo-200': '#c7d2fe',
                    'indigo-300': '#a5b4fc',
                    'indigo-400': '#818cf8',
                    'indigo-500': '#6366f1',
                    'indigo-600': '#4f46e5',
                    'indigo-700': '#4338ca',
                    'indigo-800': '#3730a3',
                    'indigo-900': '#312e81',
                    'indigo-950': '#1e1b4b',

                    // Violet
                    'violet-50': '#f5f3ff',
                    'violet-100': '#ede9fe',
                    'violet-200': '#ddd6fe',
                    'violet-300': '#c4b5fd',
                    'violet-400': '#a78bfa',
                    'violet-500': '#8b5cf6',
                    'violet-600': '#7c3aed',
                    'violet-700': '#6d28d9',
                    'violet-800': '#5b21b6',
                    'violet-900': '#4c1d95',
                    'violet-950': '#3a176e',

                    // Purple
                    'purple-50': '#faf5ff',
                    'purple-100': '#f3e8ff',
                    'purple-200': '#e9d5ff',
                    'purple-300': '#d8b4fe',
                    'purple-400': '#c084fc',
                    'purple-500': '#a855f7',
                    'purple-600': '#9333ea',
                    'purple-700': '#7e22ce',
                    'purple-800': '#6b21a8',
                    'purple-900': '#581c87',
                    'purple-950': '#43145c',

                    // Fuchsia
                    'fuchsia-50': '#fdf4ff',
                    'fuchsia-100': '#fae8ff',
                    'fuchsia-200': '#f5d0fe',
                    'fuchsia-300': '#f0abfc',
                    'fuchsia-400': '#e879f9',
                    'fuchsia-500': '#d946ef',
                    'fuchsia-600': '#c026d3',
                    'fuchsia-700': '#a21caf',
                    'fuchsia-800': '#86198f',
                    'fuchsia-900': '#701a75',
                    'fuchsia-950': '#4d0d59',

                    // Pink
                    'pink-50': '#fdf2f8',
                    'pink-100': '#fce7f3',
                    'pink-200': '#fbcfe8',
                    'pink-300': '#f9a8d4',
                    'pink-400': '#f472b6',
                    'pink-500': '#ec4899',
                    'pink-600': '#db2777',
                    'pink-700': '#be185d',
                    'pink-800': '#9d174d',
                    'pink-900': '#831843',
                    'pink-950': '#5b0e3e',

                    // Rose
                    'rose-50': '#fff1f2',
                    'rose-100': '#ffe4e6',
                    'rose-200': '#fecdd3',
                    'rose-300': '#fda4af',
                    'rose-400': '#fb7185',
                    'rose-500': '#f43f5e',
                    'rose-600': '#e11d48',
                    'rose-700': '#be123c',
                    'rose-800': '#9f1239',
                    'rose-900': '#881337',
                    'rose-950': '#4c0519',

                 },
            animation: {
                  'spin-slow': 'spin 3s linear infinite',
                    wiggle: 'wiggle 1s ease-in-out infinite',
            }

      },
      fontFamily: {
            sans: ['Graphik', 'sans-serif'],
            serif: ['Merriweather', 'serif'],
      },
  },
  variants: {
      extend: {},
  },
  plugins: [
      /**
       * '@tailwindcss/forms' is the forms plugin that provides a minimal styling
       * for forms. If you don't like it or have own styling for forms,
       * comment the line below to disable '@tailwindcss/forms'.
       */
      require('@tailwindcss/forms'),
      require('@tailwindcss/typography'),
      require('@tailwindcss/aspect-ratio'),
  ],
}