import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        accent: "#005f73",
        good: "#1b7f46",
        bad: "#b42318",
        warn: "#9a6700",
        surface: {
          DEFAULT: "#ffffff",
          dark: "#0f172a",
        },
        muted: {
          DEFAULT: "#f1f5f9",
          dark: "#1e293b",
        },
      },
      fontFamily: {
        sans: [
          "IBM Plex Sans",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
