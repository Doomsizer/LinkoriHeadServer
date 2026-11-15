import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "#070b14",
        surface: "#0e1526",
        border: "#1e2945",
        accent: "#3b82f6",
      },
    },
  },
  plugins: [],
};

export default config;
