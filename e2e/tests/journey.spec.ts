import { expect, test, type Page } from '@playwright/test';

// Каждый тест — новый пользователь: память и поездки прошлых прогонов не влияют на результат
test.beforeEach(async ({ page }, info) => {
    const user = `e2e-${info.project.name}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    await page.addInitScript((id) => {
        if (!sessionStorage.getItem('e2e-ready')) {
            localStorage.clear();
            localStorage.setItem('shturman.user', id);
            sessionStorage.setItem('e2e-ready', '1');
        }
    }, user);
});

async function say(page: Page, text: string) {
    const box = page.getByRole('textbox', { name: 'Сообщение агенту' });
    await box.fill(text);
    await box.press('Enter');
}

test('размытый запрос: одно уточнение кнопкой, направления, план', async ({ page }) => {
    await page.goto('/');
    await say(page, 'хочу к морю, недорого');
    // агент спрашивает максимум одно — и даёт ответ кнопкой
    await page.getByRole('button', { name: /вдвоём/ }).first().click();
    await expect(page.getByRole('heading', { name: /Куда поехать в/ })).toBeVisible();
    await page.getByRole('button', { name: /^Собрать/ }).first().click();
    await expect(page.getByText(/Собрал поездку/).last()).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Варианты поездки' })).toBeVisible();
});

test('конкретный запрос → календарь цен → оформление → поездка с памяткой', async ({ page }) => {
    await page.goto('/');
    await say(page, 'Сочи с 10 по 17 ноября вдвоём, бюджет 80 тысяч');
    await expect(page.getByText(/Собрал поездку в Сочи/).last()).toBeVisible();

    // календарь «а если сдвинуть заезд»: клик по другому дню пересобирает план на ту цену, что была обещана
    const strip = page.locator('.date-strip');
    await expect(strip.getByRole('button', { name: /сейчас в плане/ })).toBeVisible();
    const other = strip.getByRole('button', { name: /^Заезд \d+ \S+: [\d\s ]+₽$/ }).first();
    const promised = (await other.getAttribute('aria-label'))!.split(': ')[1];
    await other.click();
    await expect(page.getByText(/Пересобрал план, а не искал заново/).last()).toBeVisible();
    await expect(page.getByRole('button', { name: new RegExp(`Оформить «.+» за ${promised.replace(/\s/g, '\\s')}`) })).toBeVisible();

    await page.getByRole('button', { name: /^Оформить «/ }).click();
    await page.getByLabel('Имя путешественника').fill('Анна Иванова');
    await page.getByLabel('Почта для ваучера').fill('anna@example.com');
    await page.getByRole('button', { name: /Оплатить .* \(имитация\)/ }).click();
    await expect(page.getByRole('heading', { name: 'Поездка оформлена' })).toBeVisible();

    await page.getByRole('link', { name: 'Открыть поездку' }).click();
    await expect(page.getByRole('heading', { name: 'Что взять с собой' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Добавить в календарь' })).toBeVisible();
    // после покупки: перенос дат — расчёт и подтверждение
    await page.getByRole('button', { name: 'Перенести на 2 дня позже' }).click();
    await expect(page.locator('p.answer')).toContainText('Подтвердить?');
    await page.getByRole('button', { name: 'Подтвердить' }).click();
    await expect(page.locator('p.answer')).toContainText('Перенёс поездку');
});

test('не о поездке — вежливое «я про поездки», а не анкета', async ({ page }) => {
    await page.goto('/');
    await say(page, 'расскажи анекдот');
    await expect(page.getByText(/Я помогаю только с поездками/).last()).toBeVisible();
});
