/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./templates/**/*.html",
  ],
    safelist: [
        //  button.classList.toggle(`bg-${colorCategory}-100`, !isActive);
        //  button.classList.toggle(`text-${colorCategory}-700`, !isActive);
        //  button.classList.toggle(`hover:bg-${colorCategory}-200`, !isActive);
        //  button.classList.toggle(`bg-${colorCategory}-600`, isActive);
        //  button.classList.toggle('text-white', isActive);
        //  button.classList.toggle(`hover:bg-${colorCategory}-700`, isActive);
        //  button.classList.toggle('ring-2', isActive);
        //  button.classList.toggle(`ring-${colorCategory}-300`, isActive);
      { pattern: /bg-[a-z]+-\d{3}/ },        // all bg colors like bg-red-600, bg-green-200
      { pattern: /text-[a-z]+(-\d{3})?/ },  // text colors including 'text-white'
      { pattern: /hover:bg-[a-z]+-\d{3}/ }, // hover:bg-*
      { pattern: /ring(-[a-z]+)?-\d{1,3}/ }, // ring-2, ring-red-300
      { pattern: /filter-/ }, // filter-suggestion-inactive filter-<color>s
        "hidden",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
