/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/file_fetcher/web/templates/**/*.html",
  ],
  theme: {
    extend: {},
  },
  plugins: [require("daisyui")],
  daisyui: {
    themes: ["dark", "light"],
    darkTheme: "dark",
  },
};
