import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  testMatch: ['mockLearningPath.spec.mjs', 'productExperience.spec.mjs', 'phase4Repair.spec.mjs', 'round3Lesson.spec.mjs'],
  outputDir: '../.demo/playwright-learning-path',
  reporter: 'list',
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: { browserName: 'chromium', locale: 'zh-CN' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: '768px', use: { viewport: { width: 768, height: 1024 }, isMobile: true, hasTouch: true } },
    { name: '390px', use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
});
