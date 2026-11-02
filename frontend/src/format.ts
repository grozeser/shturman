const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];

export const money = (value: number) => `${Math.round(value).toLocaleString('ru-RU')} ₽`;

export const signed = (value: number) => (value > 0 ? `+${money(value)}` : value < 0 ? `−${money(-value)}` : '0 ₽');

export const time = (stamp: string) => stamp.slice(11, 16);

export function day(stamp: string): string {
    const [, month, dayOfMonth] = stamp.slice(0, 10).split('-').map(Number);
    return `${dayOfMonth} ${MONTHS_GEN[month - 1]}`;
}

export function duration(minutes: number): string {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    if (!h) return `${m} мин`;
    return m ? `${h} ч ${m} мин` : `${h} ч`;
}

export function plural(n: number, one: string, few: string, many: string): string {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
    return many;
}

export const temp = (value: number | null) => (value === null ? '—' : `${value > 0 ? '+' : ''}${value}°`);
