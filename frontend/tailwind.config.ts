import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // CrownOps 로고 기반 주황 계열 브랜드 스케일 (그라데이션 #FF7A1A → #FFAA00)
        brand: {
          50: "#FFF4E6",
          100: "#FFE6C7",
          200: "#FFCB8A",
          300: "#FFAD4D",
          400: "#FF9526",
          500: "#FF7A0A",
          600: "#F2640A",
          700: "#D14E00",
          800: "#A83C00",
          900: "#7A2C00",
        },
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #FF7A1A 0%, #FFAA00 100%)",
      },
    },
  },
  plugins: [],
};

export default config;
