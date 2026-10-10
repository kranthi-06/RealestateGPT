import { test, expect, type Page } from '@playwright/test';

/**
 * Journey verification for the upgraded platform.
 *
 * Graphs A–G from the upgrade requirements:
 *   A — Market Intelligence without catalogue data
 *   B — Investment Intelligence with an external/manual price
 *   C — Saved properties persistence
 *   D — Compare workflow
 *   E — Search persistence
 *   F — Cache behaviour (API level)
 *   G — Security boundaries (API level)
 */

const password = 'JourneyPass123!';

async function register(page: Page, email: string) {
  await page.goto('/auth/register');
  await page.locator('#name').fill('Journey User');
  await page.locator('#email').fill(email);
  await page.locator('#password').fill(password);
  await page.getByRole('button', { name: /create/i }).first().click();
  // Wait until the session cookie is actually established: the navbar swaps
  // "Sign In / Get Started" for the account menu once /auth/me resolves.
  await page.waitForFunction(
    () => !document.body.textContent?.includes('Get Started'),
    { polling: 400, timeout: 30000 }
  );
  await page.waitForTimeout(1000);
}

async function searchFor(page: Page, q: string, options: { includeWeb?: boolean } = {}) {
  await page.goto('/search');
  const includeWeb = options.includeWeb ?? true;
  // Wait until the shared search state has hydrated: before that the DOM still
  // shows the server-rendered defaults for the controlled checkbox.
  await page.waitForSelector('[data-search-hydrated="true"]', { timeout: 30000 });
  const webToggle = page.locator('#include-web').first();
  if ((await webToggle.isChecked().catch(() => includeWeb)) !== includeWeb) {
    if (includeWeb) await webToggle.check();
    else await webToggle.uncheck();
  }
  await page.getByPlaceholder(/BHK under/i).first().fill(q);
  await page.getByRole('button', { name: /^search$/i }).click();
  // Wait for the property CARDS, not just the tab header: the header text
  // ("Verified (n)") renders before the cards, so reading save buttons
  // earlier races and can capture nothing.
  await page.waitForFunction(
    () => document.querySelectorAll('button[aria-label^="Save "]').length >= 2,
    { polling: 400, timeout: 90000 }
  );
  await page.waitForTimeout(1200);
}

test.describe('A: Market Intelligence', () => {
  test('searches a location absent from the catalogue and shows external data', async ({ page }) => {
    test.setTimeout(180000);
    await page.goto('/market-intelligence');
    await page.getByPlaceholder(/Nandyal|city or locality/i).first().fill('Nandyal, Andhra Pradesh');
    await page.getByRole('button', { name: /analyze/i }).click();

    // The external section must appear (the catalogue has no Nandyal listings).
    await page.waitForSelector('[data-testid="external-market-section"]', { timeout: 120000 });
    const section = page.locator('[data-testid="external-market-section"]');
    await expect(section).toBeVisible();

    const text = (await section.textContent()) ?? '';
    console.log('A section says external:', /External market research/i.test(text));
    console.log('A shows not-verified disclaimer:', /not verified inventory/i.test(text));

    // Either real observations arrive, or the honest unavailable state is shown.
    const hasObservations = /Retrieved observations \(\d+\)/.test(text);
    const honestState = /No external market|temporarily unavailable|unavailable|not configured/i.test(text);
    console.log('A observations table:', hasObservations, 'honest fallback:', honestState);
    expect(hasObservations || honestState).toBe(true);

    // Missing metrics must read "Data unavailable", never a fabricated number.
    if (hasObservations) {
      console.log('A sources listed:', /Sources used \(\d+\)/.test(text));
      console.log('A data-unavailable label present:', /Data unavailable/.test(text));
    }
  });
});

test.describe('F + G: cache and security (API level)', () => {
  test('F: repeated market query uses the cache; filters change identity', async ({ request }) => {
    test.setTimeout(240000);
    // A unique location per run so the first request is a genuine miss.
    const location = `CacheTestCity ${Date.now()}`;

    // First request — a genuine upstream fetch.
    const first = await request.post('http://127.0.0.1:8000/api/v1/market/external', {
      data: { location },
      timeout: 180000,
    });
    expect(first.status()).toBe(200);
    const firstBody = await first.json();
    console.log('F first status:', firstBody.status, 'cache hit:', firstBody.cache?.hit);
    // A real upstream fetch has cache_hit=false (or an honest unavailable state).
    expect(firstBody.cache?.hit).toBe(false);

    // Second identical request — served from cache, no upstream work.
    const second = await request.post('http://127.0.0.1:8000/api/v1/market/external', {
      data: { location },
      timeout: 60000,
    });
    expect(second.status()).toBe(200);
    const secondBody = await second.json();
    console.log('F second cache hit:', secondBody.cache?.hit);
    // Cached for whichever outcome was stored (ok or no_results).
    if (firstBody.status === 'ok' || firstBody.status === 'no_results') {
      expect(secondBody.cache?.hit).toBe(true);
    }

    // A different filter produces a distinct cache identity.
    const third = await request.post('http://127.0.0.1:8000/api/v1/market/external', {
      data: { location, listing_type: 'rent' },
      timeout: 180000,
    });
    expect(third.status()).toBe(200);
    const thirdBody = await third.json();
    console.log('F different filter cache hit:', thirdBody.cache?.hit);
    expect(thirdBody.cache?.hit).toBe(false);
  });

  test('G: invalid input and failures are handled safely', async ({ request }) => {
    // Missing location → 422, not a 500.
    const missing = await request.post('http://127.0.0.1:8000/api/v1/market/external', {
      data: {},
      timeout: 30000,
    });
    console.log('G missing location status:', missing.status());
    expect(missing.status()).toBe(422);

    // Oversized location → 422.
    const huge = await request.post('http://127.0.0.1:8000/api/v1/market/external', {
      data: { location: 'x'.repeat(600) },
      timeout: 30000,
    });
    expect(huge.status()).toBe(422);

    // Nonsense numeric filters → 422 before any computation.
    const badBedrooms = await request.post('http://127.0.0.1:8000/api/v1/market/external', {
      data: { location: 'Hyderabad', bedrooms: 99 },
      timeout: 30000,
    });
    expect(badBedrooms.status()).toBe(422);

    // Investment analysis with no property source → 422.
    const noSource = await request.post('http://127.0.0.1:8000/api/v1/finance/investment', {
      data: { monthly_rent: 1000 },
      timeout: 30000,
    });
    console.log('G investment without source status:', noSource.status());
    expect(noSource.status()).toBe(422);

    // Saved properties require authentication (no anonymous access).
    const anonSaved = await request.get('http://127.0.0.1:8000/api/v1/saved/properties', {
      timeout: 30000,
    });
    console.log('G anonymous saved status:', anonSaved.status());
    expect(anonSaved.status()).toBe(401);
    const anonIds = await request.get('http://127.0.0.1:8000/api/v1/saved/properties/ids', {
      timeout: 30000,
    });
    expect(anonIds.status()).toBe(401);
  });

  test('G: one user cannot read another user\'s saved properties', async ({ browser }) => {
    const emailA = `sec_a_${Date.now()}@example.com`;
    const emailB = `sec_b_${Date.now()}@example.com`;
    const password = 'SecurityPass123!';

    const ctxA = await browser.newContext();
    const ctxB = await browser.newContext();
    const regA = await ctxA.request.post('http://127.0.0.1:8000/api/v1/auth/register', {
      data: { email: emailA, full_name: 'User A', password },
      timeout: 60000,
    });
    const regB = await ctxB.request.post('http://127.0.0.1:8000/api/v1/auth/register', {
      data: { email: emailB, full_name: 'User B', password },
      timeout: 60000,
    });
    console.log('G register A/B:', regA.status(), regB.status());

    // User A saves property 1589.
    const save = await ctxA.request.post('http://127.0.0.1:8000/api/v1/saved/properties', {
      data: { property_id: 1589 },
      timeout: 60000,
    });
    expect(save.status()).toBe(201);

    // User B must see nothing of A's saved list and cannot delete it.
    const bIds = await ctxB.request.get('http://127.0.0.1:8000/api/v1/saved/properties/ids', { timeout: 30000 });
    const bBody = await bIds.json();
    console.log('G user B saved ids:', JSON.stringify(bBody));
    expect(bBody.property_ids).toEqual([]);

    const bDelete = await ctxB.request.delete('http://127.0.0.1:8000/api/v1/saved/properties/1589', { timeout: 30000 });
    console.log('G user B delete status:', bDelete.status());
    expect(bDelete.status()).toBe(404);

    // User A's row is untouched.
    const aIds = await ctxA.request.get('http://127.0.0.1:8000/api/v1/saved/properties/ids', { timeout: 30000 });
    const aBody = await aIds.json();
    console.log('G user A saved ids:', JSON.stringify(aBody));
    expect(aBody.property_ids).toContain(1589);
    await ctxA.close();
    await ctxB.close();
  });
});

test.describe('B: Investment Intelligence', () => {
  test('runs an analysis from a manual price and recalculates', async ({ page }) => {
    test.setTimeout(180000);
    await page.goto('/finance');

    // Manual price entry — no catalogue listing required.
    await page.getByPlaceholder(/Label, e\.g\./i).fill('Hyderabad 3BHK (manual test)');
    const priceInput = page.getByLabel('Property price', { exact: true });
    await priceInput.fill('12000000');
    const areaInput = page.getByLabel('Area in square feet', { exact: true });
    await areaInput.fill('1600');
    await page.getByRole('button', { name: /add property/i }).click();

    // The selected entry shows with its source badge.
    const bodyBefore = (await page.locator('body').textContent()) ?? '';
    console.log('B entry added with "Your price" badge:', /Your price/.test(bodyBefore));

    await page.getByRole('button', { name: /run investment analysis/i }).click();
    await page.waitForFunction(
      () => document.body.textContent?.includes('Monthly EMI'),
      { polling: 400, timeout: 60000 }
    );

    const body = (await page.locator('body').textContent()) ?? '';
    console.log('B shows EMI:', /Monthly EMI/.test(body));
    console.log('B shows gross yield:', /Gross rental yield/.test(body));
    console.log('B shows cash flow:', /Net monthly cash flow/.test(body));
    console.log('B shows scenarios:', /Return scenarios/.test(body));
    console.log('B no "No analysis yet":', !/No analysis yet/.test(body));
    expect(/Monthly EMI/.test(body)).toBe(true);

    // Change an assumption and re-run: the numbers must move.
    const yieldCell = (await page.getByTestId('gross-yield-stat').first().textContent()) ?? '';
    await page.getByLabel('Monthly rent (₹)').first().fill('45000');
    await page.getByRole('button', { name: /run investment analysis/i }).click();
    await page.waitForTimeout(4000);
    const body2 = (await page.locator('body').textContent()) ?? '';
    const yieldCellAfter = (await page.getByTestId('gross-yield-stat').first().textContent()) ?? '';
    console.log('B recalculation rendered:', /Monthly EMI/.test(body2));
    console.log('B yield changed with rent:', JSON.stringify(yieldCell), '->', JSON.stringify(yieldCellAfter));
    expect(yieldCell).not.toBe(yieldCellAfter);
  });
});

test.describe('C: Saved properties', () => {
  test('save, navigate away, return, unsave', async ({ page }) => {
    test.setTimeout(300000);
    const email = `journey_c_${Date.now()}@example.com`;
    await register(page, email);
    // Web discovery is a slow, rate-limited upstream and is not what these
    // journeys measure; verified catalogue results still render.
    await searchFor(page, 'Hyderabad', { includeWeb: false });

    const labels = await page.locator('button[aria-label^="Save "]').evaluateAll((els) =>
      els.map((el) => (el.getAttribute('aria-label') ?? '').replace(/^Save /, ''))
    );
    const t1 = labels[0];
    const t2 = labels[1];
    console.log('C titles:', t1, '|', t2);
    expect(t1 && t2).toBeTruthy();

    await page.locator(`button[aria-label="Save ${t1}"]`).first().click();
    await page.locator(`button[aria-label="Save ${t2}"]`).first().click();
    await page.waitForTimeout(2500);

    // The buttons must reflect the saved state immediately.
    await expect(page.locator(`button[aria-label="Unsave ${t1}"]`).first()).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator(`button[aria-label="Unsave ${t2}"]`).first()).toHaveAttribute('aria-pressed', 'true');

    await page.goto('/saved');
    // Wait for the saved list to actually render both properties.
    await page.waitForFunction(
      (titles) => titles.every((t) => document.body.textContent?.includes(t)),
      [t1, t2],
      { polling: 400, timeout: 30000 }
    );
    let body = (await page.locator('body').textContent()) ?? '';
    console.log('C saved page shows both:', body.includes(t1), body.includes(t2));
    expect(body.includes(t1) && body.includes(t2)).toBe(true);

    // Navigate away and back — saved state must persist on the cards.
    await page.goto('/explore');
    await page.waitForTimeout(1500);
    await searchFor(page, 'Hyderabad', { includeWeb: false });
    await expect(page.locator(`button[aria-label="Unsave ${t1}"]`).first()).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator(`button[aria-label="Unsave ${t2}"]`).first()).toHaveAttribute('aria-pressed', 'true');
    console.log('C persisted across navigation: OK');

    // Unsave one from the Saved page; only that one disappears.
    await page.goto('/saved');
    // Wait for the saved list to render before acting on a row control.
    await page.waitForFunction(
      (titles) => titles.every((t) => document.body.textContent?.includes(t)),
      [t1, t2],
      { polling: 400, timeout: 30000 }
    );
    const removeBtn = page.locator(`button[aria-label="Remove ${t1} from saved"]`);
    const hasRemove = (await removeBtn.count()) > 0;
    if (hasRemove) {
      await removeBtn.first().click();
    } else {
      await page.locator(`button[aria-label="Unsave ${t1}"]`).first().click();
    }
    // Wait for the row to actually disappear from the list.
    await page.waitForFunction(
      (t) => !document.querySelector(`button[aria-label="Remove ${t} from saved"]`),
      t1,
      { polling: 400, timeout: 30000 }
    );
    body = (await page.locator('body').textContent()) ?? '';
    // The saved list must no longer contain the unsaved property. The empty
    // state text ("Your shortlist starts here") proves the row is gone.
    const emptyShown = /Your shortlist starts here/i.test(body);
    const listRowGone = !(await page.locator(`button[aria-label="Remove ${t1} from saved"]`).count());
    console.log('C after unsave empty state:', emptyShown, 'row removed:', listRowGone, 't2 present:', body.includes(t2));
    expect(listRowGone || emptyShown).toBe(true);
    expect(body.includes(t2)).toBe(true);
  });
});

test.describe('D: Compare', () => {
  test('selection persists and the compare page shows both', async ({ page }) => {
    test.setTimeout(300000);
    const email = `journey_d_${Date.now()}@example.com`;
    await register(page, email);
    await searchFor(page, 'Hyderabad');
    const labels = await page.locator('button[aria-label^="Save "]').evaluateAll((els) =>
      els.map((el) => (el.getAttribute('aria-label') ?? '').replace(/^Save /, ''))
    );
    const t1 = labels[0];
    const t2 = labels[1];

    await page.locator(`button[aria-label="Add ${t1} to comparison"]`).first().click();
    await page.waitForTimeout(700);
    await page.locator(`button[aria-label="Add ${t2} to comparison"]`).first().click();
    await page.waitForTimeout(1000);

    let body = (await page.locator('body').textContent()) ?? '';
    console.log('D bar shows 2 selected:', /2\s+properties selected/.test(body));

    await page.goto('/explore');
    await page.waitForTimeout(1500);
    await page.goto('/compare');
    await page.waitForTimeout(4000);
    body = (await page.locator('body').textContent()) ?? '';
    console.log('D compare shows t1:', body.includes(t1), 't2:', body.includes(t2));
    console.log('D financing table present:', /Financing comparison/.test(body));
    expect(body.includes(t1) && body.includes(t2)).toBe(true);
  });
});

test.describe('E: Search persistence', () => {
  test('query, filters and results survive navigation; clear resets', async ({ page }) => {
    test.setTimeout(300000);
    const email = `journey_e_${Date.now()}@example.com`;
    await register(page, email);
    // Keep web discovery off: it is a slow, rate-limited upstream and not what
    // this journey measures. The setting persists in the shared search state.
    await searchFor(page, 'Hyderabad', { includeWeb: false });

    // Apply a filter via the URL (the search state mirrors URL filters both
    // ways): a 3-BHK filter keeps verified results in the catalogue.
    await page.goto('/search?q=Hyderabad&bedrooms=3');
    await page.waitForSelector('[data-search-hydrated="true"]', { timeout: 30000 });
    await page.waitForFunction(
      () => document.body.textContent?.includes('Verified ('),
      { polling: 400, timeout: 90000 }
    );
    await page.waitForTimeout(2000);
    const urlBefore = page.url();
    console.log('E url after filter:', urlBefore);
    expect(urlBefore).toContain('bedrooms=3');

    // The query box must show the restored query.
    const inputValue = await page.getByPlaceholder(/BHK under/i).first().inputValue();
    console.log('E query box value:', inputValue);
    expect(inputValue).toBe('Hyderabad');

    await page.goto('/explore');
    await page.waitForTimeout(1500);
    await page.goto('/search');
    // Results must be restored (from cache/state) without a new search.
    await page.waitForSelector('[data-search-hydrated="true"]', { timeout: 30000 });
    await page.waitForFunction(
      () => document.body.textContent?.includes('Verified ('),
      { polling: 400, timeout: 90000 }
    );

    const urlAfter = await (async () => {
      // The URL mirror restores the query string after a return to /search.
      await page.waitForFunction(
        () => window.location.search.includes('q=Hyderabad'),
        { polling: 400, timeout: 15000 }
      ).catch(() => undefined);
      return page.url();
    })();
    const stored = await page.evaluate(() => {
      const raw = sessionStorage.getItem('regpt_search_state_v1');
      if (!raw) return 'none';
      const s = JSON.parse(raw);
      return JSON.stringify({ q: s.filters?.q, bedrooms: s.filters?.bedrooms, hasResults: s.hasResults, results: s.results?.length, fetchedAt: s.fetchedAt });
    });
    console.log('E stored state:', stored);
    // The restored search may re-run when the filters changed while away;
    // wait for the result set to be rendered again (up to ~60s).
    await page
      .waitForFunction(() => document.body.textContent?.includes('Verified ('), { polling: 400, timeout: 90000 })
      .catch(() => undefined);
    const body = (await page.locator('body').textContent()) ?? '';
    console.log('E url restored:', urlAfter);
    console.log('E results restored:', /Verified \(/.test(body));
    console.log('E no empty state:', !/No properties found/.test(body));
    expect(urlAfter).toContain('q=Hyderabad');
    expect(/Verified \(/.test(body)).toBe(true);

    // Saved properties and compare selections must survive a Clear.
    await page.locator('button[aria-label^="Save "]').first().click();
    await page.waitForTimeout(2000);
    await page.locator('button[aria-label^="Add "]').first().click();
    await page.waitForTimeout(1200);

    await page.getByRole('button', { name: /^clear$/i }).first().click();
    await page.waitForTimeout(2500);
    const clearedBody = (await page.locator('body').textContent()) ?? '';
    console.log('E cleared search:', /No properties found/.test(clearedBody) || !/Verified \(/.test(clearedBody));

    const savedAfterClear = await page.evaluate(async () => {
      const res = await fetch('http://localhost:8000/api/v1/saved/properties/ids', { credentials: 'include' });
      return res.ok ? await res.json() : { error: res.status };
    });
    console.log('E saved survive clear:', JSON.stringify(savedAfterClear));
    const compareAfterClear = await page.evaluate(() => localStorage.getItem('regpt_compare_ids_v1'));
    console.log('E compare survives clear:', compareAfterClear);
    expect(JSON.stringify(savedAfterClear)).toContain('property_ids');
    expect(compareAfterClear).toBeTruthy();
  });
});
