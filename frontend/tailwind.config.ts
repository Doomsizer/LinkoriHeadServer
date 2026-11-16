import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "#120b28",
        bgDeep: "#1b1238",
        accent: "#7ae9eb",
        pinkAccent: "#f472b6",
        muted: "#9e96cc",
      },
    },
  },
  plugins: [],
};

export default config;