// Optional browser check: install Playwright, then run against a local docs server.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({
    ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}),
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(process.env.STUDIO_URL || 'http://127.0.0.1:5174');
  await page.waitForFunction(() => !document.querySelector('#download').disabled);
  for (const effect of ['film', 'sepia', 'duotone', 'vignette', 'segments', 'primary', 'halftone', 'edge', 'mirror', 'rotate']) {
    await page.locator(`[data-effect="${effect}"]`).click();
    assert.equal(await page.locator(`[data-effect="${effect}"]`).getAttribute('aria-pressed'), 'true');
    assert(await page.locator('#after').evaluate(canvas => canvas.width > 0 && canvas.height > 0));
  }
  await page.locator('[data-effect="edge"]').click();
  await page.locator('#threshold').fill('15');
  await page.locator('#threshold').dispatchEvent('input');
  assert.equal(await page.locator('#threshold-value').textContent(), '15');
  await page.locator('#comparison').fill('25');
  await page.locator('#comparison').dispatchEvent('input');
  assert((await page.locator('#compare-stage').getAttribute('style')).includes('25%'));
  for (const file of ['fox.jpg', 'alpine-lake.jpg', 'fern.jpg', 'butterfly.jpg', 'cheerful-puppy.png']) {
    await page.locator(`[data-sample="${file}"]`).click();
    await page.waitForFunction(file => document.querySelector(`[data-sample="${file}"]`).getAttribute('aria-pressed') === 'true', file);
  }
  await page.locator('#photo-input').setInputFiles(path.join(__dirname, '../docs/samples/fern.jpg'));
  await page.waitForFunction(() => document.querySelector('#image-name').textContent === 'fern.jpg');
  const downloading = page.waitForEvent('download');
  await page.locator('#download').click();
  const download = await downloading;
  assert(download.suggestedFilename().endsWith('.png'));
  assert.equal(await download.failure(), null);
  await page.locator('#reset').click();
  await page.waitForFunction(() => document.querySelector('#image-name').textContent.includes('Generated sample'));
  await page.evaluate(() => document.querySelectorAll('img').forEach(image => image.loading = 'eager'));
  await page.waitForFunction(() => [...document.images].every(image => image.complete && image.naturalWidth > 0));
  await page.mouse.move(0, 0);
  await page.locator('#playground').screenshot({ path: path.join(__dirname, '../docs/media/site-preview.jpg'), type: 'jpeg', quality: 88 });
  await page.screenshot({ path: '/private/tmp/photo-studio-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: '/private/tmp/photo-studio-mobile.png', fullPage: true });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.deepEqual(errors, []);
  console.log('Passed: 10 effects, 5 sample selections, threshold, divider, local image, PNG download, reset, all assets, mobile layout.');
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
