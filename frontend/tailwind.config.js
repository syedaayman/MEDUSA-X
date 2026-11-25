/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#142b3b",
        muted: "#657786",
        teal: "#168c88",
        mist: "#f4f8fa",
      },
    },
  },
  plugins: [],
};
