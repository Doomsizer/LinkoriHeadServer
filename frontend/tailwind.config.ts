import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "#1b1238",
        surface: "rgba(255, 255, 255, 0.045)",
        border: "rgba(255, 255, 255, 0.09)",
        accent: "#7ae9eb",
        accent2: "#7ab1eb",
        muted: "#a8a2d4",
      },
    },
  },
  plugins: [],
};

export default config;

