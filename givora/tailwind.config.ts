import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Palette Givora : chaud, lisible en plein soleil sur un téléphone.
        ink: "#1B1420",
        cream: "#FFF8F2",
        coral: { DEFAULT: "#FF5A5F", dark: "#E04146" },
        mint: "#0FA97F",
      },
      fontFamily: {
        sans: ["var(--font-archivo)", "Helvetica Neue", "Arial", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
