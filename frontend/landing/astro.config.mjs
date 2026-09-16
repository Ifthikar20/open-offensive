import { defineConfig } from 'astro/config';

// Static marketing site. `site` is used for canonical URLs / sitemap.
// Inline the small stylesheet so each page is a single self-contained file.
export default defineConfig({
  site: 'https://openoffensive.ai',
  build: { inlineStylesheets: 'always' },
});
