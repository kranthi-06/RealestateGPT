import { test, expect } from '@playwright/test';

test.describe('Critical User Journeys', () => {
  test('landing page loads and has key elements', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/RealEstateGPT/i);
    await expect(page.getByRole('link', { name: /explore/i }).first()).toBeVisible();
  });

  test('search page loads and shows search input', async ({ page }) => {
    await page.goto('/search');
    await expect(page.getByPlaceholder(/3BHK|search/i).first()).toBeVisible();
  });

  test('login page has form fields', async ({ page }) => {
    await page.goto('/auth/login');
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
  });

  test('register page has form fields', async ({ page }) => {
    await page.goto('/auth/register');
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/name/i).first()).toBeVisible();
  });

  test('navigation links work', async ({ page }) => {
    await page.goto('/');
    
    // Click search link
    await page.getByRole('link', { name: /explore/i }).first().click();
    await expect(page).toHaveURL(/\/search/);

    // Navigate to assistant directly (should redirect or show login)
    await page.goto('/assistant');
    await expect(page).toHaveURL(/\/assistant|login/);
  });

  test('mobile viewport shows responsive layout', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    
    // Hero should be visible
    await expect(page.locator('h1').first()).toBeVisible();
    
    // Navigate to search
    await page.goto('/search');
    await expect(page.getByPlaceholder(/3BHK|search/i).first()).toBeVisible();
  });
});
