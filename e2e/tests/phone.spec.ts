import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
    const user = `e2e-phone-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    await page.addInitScript((id) => {
        if (!sessionStorage.getItem('e2e-ready')) {
            localStorage.clear();
            localStorage.setItem('shturman.user', id);
            sessionStorage.setItem('e2e-ready', '1');
        }
    }, user);
});

test('телефон: чат и план — вкладками, страница без горизонтальной прокрутки', async ({ page }) => {
    await page.goto('/');
    const box = page.getByRole('textbox', { name: 'Сообщение агенту' });
    await box.fill('Анталья в мае вдвоём');
    await box.press('Enter');
    await expect(page.getByText(/Собрал поездку в Анталье/).last()).toBeVisible();
    await page.getByRole('button', { name: /^План/ }).click();
    await expect(page.getByRole('heading', { name: 'Варианты поездки' })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
});
