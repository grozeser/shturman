import { plural } from '../format';
import type { Savings as SavingsData } from '../types';
import Icon from './Icon';
import './Savings.css';

function hours(minutes: number) {
    if (minutes < 55) return `${Math.max(5, Math.round(minutes / 5) * 5)} мин`;
    return `${(Math.round(minutes / 30) / 2).toLocaleString('ru-RU')} ч`;
}

// «Сколько времени вы сэкономили»: цифры — из следа агента, ручной путь — оценка по формуле в подсказке
export default function Savings({ savings, compact }: { savings: SavingsData; compact?: boolean }) {
    const tiles: [number, string, string, string][] = [
        [savings.destinations, 'направление', 'направления', 'направлений'],
        [savings.hotels, 'отель', 'отеля', 'отелей'],
        [savings.transport, 'вариант дороги', 'варианта дороги', 'вариантов дороги'],
        [savings.dates, 'дата заезда', 'даты заезда', 'дат заезда'],
        [savings.checks, 'стыковка', 'стыковки', 'стыковок'],
    ];
    const said = savings.messages + savings.taps;
    return (
        <section className={`card savings${compact ? ' compact' : ''}`} aria-labelledby="savings-title">
            <header>
                <h2 id="savings-title">
                    <Icon name="sparkle" size={18} /> Сэкономили около {hours(savings.minutes)}
                </h2>
                <span
                    className="muted"
                    title={`Оценка ручного пути: поиск на ${savings.sites} сайтах (билеты, отели, трансферы, погода, визы) по 4 действия, открыть каждый сравнённый вариант (не больше, чем открыл бы человек) и сверить каждую стыковку. Полминуты на страницу, три минуты на сверку.`}
                >
                    {said} {plural(said, 'шаг', 'шага', 'шагов')} в чате вместо {Math.floor(savings.clicks / 10) * 10}+ кликов по {savings.sites} сайтам
                </span>
            </header>
            {!compact && (
                <ul className="savings-tiles">
                    {tiles
                        .filter(([n]) => n > 0)
                        .map(([n, one, few, many]) => (
                            <li key={one}>
                                <b>{n}</b>
                                <span>{plural(n, one, few, many)}</span>
                            </li>
                        ))}
                </ul>
            )}
            <p className="savings-line">{savings.line}.</p>
        </section>
    );
}
