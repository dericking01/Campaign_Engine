import type { Config } from "tailwindcss";

// Brand colors sampled directly from the official AfyaCall logo
// (https://www.afyacall.co.tz/images/afyaCall-logo.png): a deep teal
// (#0F3F43) and a fresh lime green (#AACE3A). Everything else in this
// palette is built around those two, deliberately light-theme only.
const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef7f3",
          100: "#d7ebe2",
          200: "#adcfc9",
          300: "#7fb0ab",
          400: "#4f8c8a",
          500: "#1f6b6b",
          600: "#155457",
          700: "#123f42",
          800: "#0f3f43", // logo teal
          900: "#0a2c2f",
          950: "#061c1e",
        },
        lime: {
          50: "#f6faec",
          100: "#e9f4cd",
          200: "#d5eb9f",
          300: "#bcdd69",
          400: "#aace3a", // logo green
          500: "#93bf28",
          600: "#729720",
          700: "#57731e",
          800: "#485c1e",
          900: "#3d4e1e",
        },
        ink: {
          DEFAULT: "#16211f",
          muted: "#5b6b68",
          faint: "#8b9997",
        },
        surface: {
          DEFAULT: "#ffffff",
          subtle: "#f7f8f6",
          sunken: "#f1f3f0",
        },
        line: {
          DEFAULT: "#e6e9e5",
          strong: "#d3d8d1",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-inter)",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      boxShadow: {
        soft: "0 1px 2px 0 rgb(15 63 67 / 0.04), 0 1px 3px 0 rgb(15 63 67 / 0.06)",
        card: "0 1px 2px 0 rgb(15 63 67 / 0.04), 0 4px 16px -4px rgb(15 63 67 / 0.08)",
        lifted: "0 8px 24px -6px rgb(15 63 67 / 0.16), 0 2px 8px -2px rgb(15 63 67 / 0.08)",
        glow: "0 0 0 4px rgb(170 206 58 / 0.16)",
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.25rem",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.97)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.4s ease-out",
        "slide-up": "slide-up 0.45s cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-in": "scale-in 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
