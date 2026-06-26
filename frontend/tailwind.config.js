/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // светлая пастельная база
        canvas: "#f5f4f8", // фон приложения (мягкий лавандово-серый)
        surface: "#ffffff", // карточки/панели
        line: "#e9e8f1", // границы
        // тёплый глиняный акцент темы «Феникс» (пастельный)
        clay: {
          50: "#fdf5f1",
          100: "#fae9e1",
          200: "#f3cebf",
          300: "#e9ac96",
          400: "#dd8a6c",
          500: "#cd6c4c",
          600: "#b1573a",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.25s ease-out",
      },
    },
  },
  plugins: [],
};
