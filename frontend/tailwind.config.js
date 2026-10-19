/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Height-based breakpoints: the sign-in pages compact themselves to fit one screen.
      screens: {
        short: { raw: "(max-height: 820px)" },
        tiny: { raw: "(max-height: 680px)" },
        "short-phone": { raw: "(max-width: 639px) and (max-height: 820px)" },
        "tiny-phone": { raw: "(max-width: 639px) and (max-height: 680px)" },
      },
      fontFamily: { sans: ['"Plus Jakarta Sans"', "Inter", "system-ui", "Segoe UI", "sans-serif"] },
      colors: {
        forest: { 950: "#0b2a1a", 900: "#0f3a24", 800: "#14492e", 700: "#1a5c3a", 600: "#1f7044" },
        leaf: { 50: "#f1f8f3", 100: "#e1f0e6", 200: "#c4e1cd", 500: "#2e9d5b", 600: "#1f8a4c", 700: "#18713e" },
        mint: { 50: "#f5faf6", 100: "#eaf4ed" },
        // Sign-in / registration palette: warm cream, soft sage, matcha and a lime accent.
        cream: { 50: "#fbfaf4", 100: "#f5f2e6" },
        sage: { 100: "#e6ede2", 200: "#d2dfcc", 400: "#9fb596", 600: "#62805a" },
        matcha: { 400: "#9cc165", 500: "#7fa64a" },
        lime: { 300: "#d4ea7a", 400: "#bedc4b" },
        amber: { 50: "#fff8e8", 100: "#fdefc8", 500: "#e0a106", 600: "#b97f00", 700: "#8f6200" },
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,58,36,.05), 0 4px 16px -8px rgba(16,58,36,.12)",
        lift: "0 2px 4px rgba(16,58,36,.06), 0 12px 28px -12px rgba(16,58,36,.22)",
      },
      // One timing scale and one easing curve for every animation in the app.
      transitionTimingFunction: { smooth: "cubic-bezier(0.22, 1, 0.36, 1)" },
      transitionDuration: { 250: "250ms" },
      keyframes: {
        "fade-up": { from: { opacity: "0", transform: "translateY(8px)" }, to: { opacity: "1", transform: "none" } },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        // Page transitions animate opacity only: a transform would make the page the containing
        // block of position: fixed children (dialogs, drawers) while the animation is in effect.
        "page-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "scale-in": { from: { opacity: "0", transform: "scale(.96)" }, to: { opacity: "1", transform: "none" } },
        "slide-in-right": { from: { opacity: "0", transform: "translateX(24px)" }, to: { opacity: "1", transform: "none" } },
        "slide-down": { from: { opacity: "0", transform: "translateY(-6px)" }, to: { opacity: "1", transform: "none" } },
        shake: { "0%,100%": { transform: "none" }, "25%": { transform: "translateX(-4px)" }, "75%": { transform: "translateX(4px)" } },
        // Detect page: scanning line moving over the leaf image (only while it is being analysed)
        scan: { "0%": { top: "0%" }, "100%": { top: "100%" } },
      },
      animation: {
        "fade-up": "fade-up 320ms cubic-bezier(0.22, 1, 0.36, 1) both",
        scan: "scan 1.8s ease-in-out infinite alternate",
        "fade-in": "fade-in 200ms ease-out both",
        "page-in": "page-in 220ms ease-out",
        "scale-in": "scale-in 180ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "slide-in-right": "slide-in-right 260ms cubic-bezier(0.22, 1, 0.36, 1) both",
        "slide-down": "slide-down 180ms cubic-bezier(0.22, 1, 0.36, 1) both",
        shake: "shake 280ms ease-in-out",
      },
    },
  },
  plugins: [],
};
