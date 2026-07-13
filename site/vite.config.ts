import { defineConfig } from 'vite';

// Relative base so the built site works from any subpath on GitHub Pages.
export default defineConfig({
  base: './',
  build: {
    target: 'esnext',
    cssMinify: true,
    modulePreload: { polyfill: false },
    rollupOptions: {
      output: {
        // Split the WebGL library out so the initial parse stays lean.
        manualChunks: {
          three: ['three'],
          motion: ['gsap', 'lenis'],
        },
      },
    },
  },
});
