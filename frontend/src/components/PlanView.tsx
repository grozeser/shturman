import { useEffect, useState } from 'react';
import { api, type DateOption } from '../api';
import { day, duration, money, plural, signed, time } from '../format';
import type { Bundle, Check, ConversationState, Diff, Plan, Transport } from '../types';
import Caught from './Caught';
import Cover, { HotelPhoto, hotelPhotoPicker, type HotelPhotoItem } from './Cover';
import ForecastCard from './ForecastCard';
import GroupTrip from './GroupTrip';
import Hacks from './Hacks';
import Icon, { type IconName } from './Icon';
import TripMap from './TripMap';

type Send = (body: { action: Record<string, unknown> }, label?: string) => void;

const STATUS_ICON: Record<Check['status'], IconName> = { ok: 'check', fixed: 'wrench', warn: 'warn', error: 'close' };
const MEAL_NAMES: Record<string, string> = { RO: 'без питания', BB: 'завтраки', HB: 'полупансион', AI: 'всё включено' };

function stars(n: number) {
    return '★'.repeat(n);
}

// Слово к оценке и запятая в числе («Отлично 8,8»)
function ratingWord(rating: number) {
    return rating >= 9 ? 'Превосходно' : rating >= 8.5 ? 'Отлично' : rating >= 8 ? 'Очень хорошо' : rating >= 7 ? 'Хорошо' : 'Неплохо';
}

const MODE_ICON: Record<string, IconName> = { flight: 'plane', train: 'train', bus: 'bus', car: 'car' };

function transportLine(t: Transport) {
    if (t.mode === 'train') return `${t.carrier} ${t.number}, ${t.class.toLowerCase()}`;
    if (t.mode === 'bus' || t.mode === 'car') return `${t.carrier}${t.mode === 'bus' ? `, ${t.number}` : ''}`;
    return `${t.carrier} ${t.number}${t.stops ? `, пересадка в ${t.via} (${duration(t.layover_min)})` : ', прямой'}${t.baggage ? ', багаж включён' : ', без багажа'}`;
}

export function DiffBanner({ diff }: { diff: Diff }) {
    if (!diff.changes.length) return null;
    return (
        <section className="card diff">
            <header>
                <h2>Что изменилось</h2>
                <b className={diff.delta > 0 ? 'up' : diff.delta < 0 ? 'down' : ''}>
                    {money(diff.total_before)} → {money(diff.total_after)} ({signed(diff.delta)})
                </b>
            </header>
            <ul>
                {diff.changes.map((change) => (
                    <li key={change.part}>
                        <span className="part">{change.part}</span>
                        <s>{change.before}</s>
                        <span className="arrow">→</span>
                        <span>{change.after}</span>
                        {change.delta ? <b className={change.delta > 0 ? 'up' : 'down'}>{signed(change.delta)}</b> : null}
                    </li>
                ))}
            </ul>
            {diff.kept.filter((k) => k !== 'Доплаты').length > 0 && <p className="muted">Без изменений: {diff.kept.filter((k) => k !== 'Доплаты').join(', ').toLowerCase()}</p>}
        </section>
    );
}

function BundleCard({ bundle, selected, onSelect, busy, photo }: { bundle: Bundle; selected: boolean; onSelect: () => void; busy: boolean; photo: HotelPhotoItem | null }) {
    const issues = bundle.checks.filter((c) => c.status === 'warn' || c.status === 'error').length;
    const fixed = bundle.checks.filter((c) => c.status === 'fixed').length;
    return (
        <article className={`bundle ${bundle.style} ${selected ? 'selected' : ''}`} onClick={() => !busy && !selected && onSelect()}>
            <HotelPhoto photo={photo} height={124} />
            <div className="bundle-head">
                <span className="label">{bundle.label}</span>
                <span className="fit" title="Насколько отель подходит именно вам, без учёта цены">
                    {bundle.fit}/100
                </span>
            </div>
            <div className="total">{money(bundle.total)}</div>
            <div className="muted">{money(bundle.per_person)} на человека · дорога, отель и трансфер</div>
            <dl>
                <dt title="Дорога">
                    <Icon name={MODE_ICON[bundle.outbound.mode] ?? 'plane'} size={16} />
                </dt>
                <dd>
                    {time(bundle.outbound.depart)} → {time(bundle.outbound.arrive)}, {duration(bundle.outbound.duration_min)}
                </dd>
                <dt title="Отель">
                    <Icon name="bed" size={16} />
                </dt>
                <dd>
                    {bundle.hotel.name} <span className="stars">{stars(bundle.hotel.stars)}</span>
                </dd>
                <dt title="Питание">
                    <Icon name="meal" size={16} />
                </dt>
                <dd>{bundle.hotel.meal_label}</dd>
                <dt title="Трансфер">
                    <Icon name="car" size={16} />
                </dt>
                <dd>{bundle.transfer_in.title}</dd>
            </dl>
            <ul className="why">
                {bundle.why.slice(1, 4).map((w) => (
                    <li key={w}>{w}</li>
                ))}
            </ul>
            {bundle.sacrifices.length > 0 && (
                <ul className="cons">
                    {bundle.sacrifices.slice(0, 3).map((s) => (
                        <li key={s}>{s}</li>
                    ))}
                </ul>
            )}
            <div className="checks-mini">
                {fixed > 0 && (
                    <span className="fixed">
                        <Icon name="wrench" size={14} /> исправлено: {fixed}
                    </span>
                )}
                {issues > 0 ? (
                    <span className="warn">
                        <Icon name="warn" size={14} /> внимания: {issues}
                    </span>
                ) : (
                    <span className="ok">
                        <Icon name="check" size={14} /> стыковки в порядке
                    </span>
                )}
            </div>
            {!selected && <button disabled={busy}>Выбрать</button>}
        </article>
    );
}

function Compare({ bundles, selected }: { bundles: Bundle[]; selected: number }) {
    const rows: [string, (b: Bundle) => string][] = [
        ['Итого', (b) => money(b.total)],
        ['Транспорт', (b) => money(b.costs.transport)],
        ['Отель', (b) => money(b.costs.hotel)],
        ['Питание', (b) => (b.costs.meals ? money(b.costs.meals) : b.hotel.meal === 'AI' ? 'в цене' : '—')],
        ['Трансферы', (b) => money(b.costs.transfers)],
        ['Доплаты', (b) => (b.costs.extras ? money(b.costs.extras) : '—')],
        ['В пути туда', (b) => duration(b.outbound.duration_min) + (b.outbound.stops ? ' с пересадкой' : '')],
        ['Вылет / прилёт', (b) => `${time(b.outbound.depart)} / ${time(b.outbound.arrive)}`],
        ['До моря', (b) => (b.hotel.beach_m === null ? '—' : b.hotel.beach_m < 1000 ? `${b.hotel.beach_m} м` : `${(b.hotel.beach_m / 1000).toFixed(1)} км`)],
        ['Рейтинг отеля', (b) => `${b.hotel.rating} · ${b.hotel.reviews} отзывов`],
        ['Отмена', (b) => (b.hotel.refundable && b.hotel.free_cancel_until ? `бесплатно до ${day(b.hotel.free_cancel_until)}` : 'невозвратный')],
        ['Детский клуб', (b) => (b.hotel.features.kids_club ? 'есть' : 'нет')],
        ['Подходит вам', (b) => `${b.fit}/100`],
    ];
    return (
        <div className="compare-wrap">
            <table className="compare">
                <thead>
                    <tr>
                        <th />
                        {bundles.map((b, i) => (
                            <th key={b.id} className={i === selected ? 'sel' : ''}>
                                {b.label}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map(([name, get]) => (
                        <tr key={name}>
                            <th>{name}</th>
                            {bundles.map((b, i) => (
                                <td key={b.id} className={i === selected ? 'sel' : ''}>
                                    {get(b)}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

const PRIORITY_LABELS: [string, string, string][] = [
    ['price', 'Цена', 'дешевле'],
    ['comfort', 'Комфорт отеля', 'лучше отель'],
    ['speed', 'Время в пути', 'быстрее'],
    ['beach', 'Близость к морю', 'ближе'],
    ['flex', 'Гибкость отмены', 'с отменой'],
];

function Priorities({ priorities, onApply, busy }: { priorities: Record<string, number>; onApply: (p: Record<string, number>) => void; busy: boolean }) {
    const [local, setLocal] = useState(priorities);
    useEffect(() => {
        setLocal(priorities);
    }, [priorities]);
    const dirty = PRIORITY_LABELS.some(([key]) => Math.abs((local[key] ?? 0.5) - (priorities[key] ?? 0.5)) > 0.01);
    return (
        <section className="card priorities">
            <header>
                <h2>Что для вас важнее</h2>
                <span className="muted">агент пересоберёт варианты по вашим весам</span>
            </header>
            {PRIORITY_LABELS.map(([key, label, hint]) => (
                <label key={key}>
                    <span>{label}</span>
                    <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={local[key] ?? 0.5}
                        onChange={(e) => setLocal({ ...local, [key]: Number(e.target.value) })}
                        aria-label={label}
                    />
                    <small>{Math.round((local[key] ?? 0.5) * 100)}% · {hint}</small>
                </label>
            ))}
            <button className="primary" disabled={!dirty || busy} onClick={() => onApply(local)}>
                Пересобрать с этими весами
            </button>
        </section>
    );
}

function Timeline({ bundle, send, busy, title }: { bundle: Bundle; send: Send; busy: boolean; title?: string }) {
    const out = bundle.outbound;
    const back = bundle.inbound;
    const early = bundle.extras.find((e) => e.type === 'early_checkin' || e.type === 'extra_night');
    const late = bundle.extras.find((e) => e.type === 'late_checkout');
    const items: { when: string; icon: IconName; title: string; text: string; price?: number }[] = [
        { when: `${day(out.depart)}, ${time(out.depart)}`, icon: MODE_ICON[out.mode] ?? 'plane', title: `${out.from} → ${out.to}`, text: `${transportLine(out)} · ${duration(out.duration_min)}${out.included ? ' · оплачен в предыдущей части' : ''}`, price: out.included ? undefined : out.cost },
        { when: time(out.arrive), icon: 'pin', title: `Прибытие: ${out.to}`, text: out.night ? 'ночное прибытие' : '' },
        { when: '', icon: 'car', title: bundle.transfer_in.title, text: `${duration(bundle.transfer_in.duration_min)}${bundle.transfer_in.child_seat ? ' · детское кресло' : ''}`, price: bundle.transfer_in.price },
        { when: early ? 'сразу' : bundle.hotel.checkin, icon: 'key', title: `Заселение: ${bundle.hotel.name}`, text: early ? `${early.title} (${money(early.price)})` : `${bundle.hotel.area}, ${bundle.hotel.meal_label}`, price: undefined },
        { when: `${bundle.nights} ноч.`, icon: 'sun', title: 'Отдых', text: bundle.hotel.pros.slice(0, 3).join(' · ') },
        { when: `${day(bundle.checkout)}, ${late ? 'до 18:00' : bundle.hotel.checkout}`, icon: 'suitcase', title: 'Выезд из отеля', text: late ? late.title : '' },
        { when: '', icon: 'car', title: bundle.transfer_out.title, text: duration(bundle.transfer_out.duration_min), price: bundle.transfer_out.price },
        { when: `${time(back.depart)} → ${time(back.arrive)}`, icon: MODE_ICON[back.mode] ?? 'plane', title: `${back.from} → ${back.to}`, text: `${transportLine(back)} · ${duration(back.duration_min)}`, price: back.cost },
    ];
    return (
        <section className="card">
            <header>
                <h2>
                    {title ? `${title}, ` : 'План: '}
                    {day(bundle.checkin)} – {day(bundle.checkout)}
                </h2>
                <span className="muted">«{bundle.label}», {money(bundle.total)}</span>
            </header>
            <ol className="timeline">
                {items.map((item, index) => (
                    <li key={index}>
                        <span className="when">{item.when}</span>
                        <span className="icon">
                            <Icon name={item.icon} size={16} />
                        </span>
                        <div>
                            <b>{item.title}</b>
                            {item.text && <span>{item.text}</span>}
                        </div>
                        {item.price !== undefined && <span className="cost">{money(item.price)}</span>}
                    </li>
                ))}
            </ol>
            <h3 className="sub">Проверка стыковок</h3>
            <ul className="checks">
                {bundle.checks.map((check) => (
                    <li key={check.id} className={check.status}>
                        <span className="st">
                            <Icon name={STATUS_ICON[check.status]} size={14} />
                        </span>
                        <div>
                            <b>{check.title}</b>
                            <span>{check.detail}</span>
                        </div>
                        {check.fix && (
                            <button disabled={busy} onClick={() => send({ action: { type: 'apply_fix', fix: check.fix } }, check.fix!.label)}>
                                {check.fix.label}
                            </button>
                        )}
                    </li>
                ))}
            </ul>
        </section>
    );
}

function Alternatives({ plan, bundle, send, busy, photos }: { plan: Plan; bundle: Bundle; send: Send; busy: boolean; photos: Map<string, HotelPhotoItem | null> }) {
    const [tab, setTab] = useState<'hotels' | 'out' | 'back' | 'options'>('hotels');
    const swap = (part: string, value: unknown, label: string) => send({ action: { type: 'swap', part, value } }, label);
    const transports = (list: Transport[], current: Transport, part: string) => (
        <ul className="alt-list">
            {list.map((t) => (
                <li key={t.id} className={t.id === current.id ? 'current' : ''}>
                    <div>
                        <b>
                            {time(t.depart)} → {time(t.arrive)} · {duration(t.duration_min)}
                        </b>
                        <span>
                            {transportLine(t)}
                            {t.night ? ' · ночной' : ''}
                        </span>
                    </div>
                    <span className="cost">{money(t.price)} / чел.</span>
                    {t.id === current.id ? <span className="tag">в плане</span> : <button disabled={busy} onClick={() => swap(part, t.id, `${t.number} в ${time(t.depart)}`)}>Выбрать</button>}
                </li>
            ))}
        </ul>
    );
    return (
        <section className="card">
            <header>
                <h2>Поменять часть поездки</h2>
                <span className="muted">остальное останется как есть</span>
            </header>
            <div className="tabs" role="tablist">
                {(
                    [
                        ['hotels', `Отели (${plan.hotels.length})`],
                        ['out', 'Туда'],
                        ['back', 'Обратно'],
                        ['options', 'Питание и отмена'],
                    ] as const
                ).map(([key, label]) => (
                    <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'on' : ''} onClick={() => setTab(key)}>
                        {label}
                    </button>
                ))}
            </div>
            {tab === 'hotels' && (
                <>
                    <ul className="alt-list hotels">
                        {plan.hotels.map((h) => (
                            <li key={h.id} className={`hotel-row ${h.id === bundle.hotel.id ? 'current' : ''}`}>
                                <HotelPhoto photo={photos.get(h.id)} height={84} />
                                <div>
                                    <b>
                                        {h.name} <span className="stars">{stars(h.stars)}</span>
                                    </b>
                                    <span>
                                        {h.area}
                                        {h.beach_m !== null ? ` · ${h.beach_m} м до моря` : ''} · {h.meal_label}
                                    </span>
                                    {h.pros.length > 0 && <span className="pros">+ {h.pros.slice(0, 3).join(', ')}</span>}
                                    {h.cons.length > 0 && <span className="minus">− {h.cons.slice(0, 2).join(', ')}</span>}
                                    {h.not_for.length > 0 && <span className="notfor">Не подойдёт: {h.not_for.slice(0, 2).join(', ')}</span>}
                                </div>
                                <div className="hotel-score" title={`Оценка гостей: ${h.rating} из 10`}>
                                    <span>
                                        <b>{ratingWord(h.rating)}</b>
                                        <small>
                                            {h.reviews.toLocaleString('ru-RU')} {plural(h.reviews, 'отзыв', 'отзыва', 'отзывов')}
                                        </small>
                                    </span>
                                    <span className="rating">{h.rating.toFixed(1).replace('.', ',')}</span>
                                </div>
                                <div className="hotel-row-end">
                                    <span className="fit" title="Насколько отель подходит именно вам">
                                        {h.fit}/100
                                    </span>
                                    <span className="cost">{money(h.price_total)}</span>
                                    {h.id === bundle.hotel.id ? <span className="tag">в плане</span> : <button disabled={busy} onClick={() => swap('hotel_id', h.id, `Отель «${h.name}»`)}>Выбрать</button>}
                                </div>
                            </li>
                        ))}
                    </ul>
                    {plan.hotels_rejected.length > 0 && (
                        <div className="rejected">
                            <b>Отсеял ({plan.hotels_rejected.length}):</b>
                            {plan.hotels_rejected.slice(0, 8).map((r) => (
                                <span key={r.id}>
                                    {r.name} {stars(r.stars)} — {r.reason}
                                </span>
                            ))}
                        </div>
                    )}
                </>
            )}
            {tab === 'out' && transports(plan.outbound, bundle.outbound, 'outbound_id')}
            {tab === 'back' && transports(plan.inbound, bundle.inbound, 'inbound_id')}
            {tab === 'options' && (
                <div className="options">
                    <div>
                        <span>Питание</span>
                        {bundle.hotel.meals.map((meal) => (
                            <button key={meal} disabled={busy || meal === bundle.hotel.meal} className={meal === bundle.hotel.meal ? 'on' : ''} onClick={() => swap('meal', meal, `Питание: ${MEAL_NAMES[meal]}`)}>
                                {MEAL_NAMES[meal]}
                            </button>
                        ))}
                    </div>
                    <div>
                        <span>Тариф</span>
                        <button disabled={busy || bundle.hotel.refundable} className={bundle.hotel.refundable ? 'on' : ''} onClick={() => swap('refundable', true, 'Тариф с бесплатной отменой')}>
                            с бесплатной отменой
                        </button>
                        <button disabled={busy || !bundle.hotel.refundable} className={!bundle.hotel.refundable ? 'on' : ''} onClick={() => swap('refundable', false, 'Невозвратный тариф')}>
                            невозвратный (дешевле)
                        </button>
                    </div>
                    <div>
                        <span>Трансфер</span>
                        {(
                            [
                                ['shuttle', 'групповой'],
                                ['taxi', 'такси'],
                                ['private', 'индивидуальный'],
                                // минивэн с подъёмником есть только в поездках с доступной средой — у них есть проверка «lift»
                                ...(bundle.checks.some((c) => c.id === 'lift') ? [['accessible', 'с подъёмником'] as const] : []),
                            ] as const
                        ).map(([kind, label]) => (
                            <button key={kind} disabled={busy || bundle.transfer_in.kind === kind} className={bundle.transfer_in.kind === kind ? 'on' : ''} onClick={() => swap('transfer_kind', kind, `Трансфер: ${label}`)}>
                                {label}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </section>
    );
}

const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const LOADING_DAYS: DateOption[] = [-3, -2, -1, 0, 1, 2, 3].map((offset) => ({ offset, date: '', available: false, total: null, delta: null, same_hotel: null, cheapest: false }));

// Та же поездка с заездом на ±3 дня: цена от двери до двери, клик пересобирает план на этот день
function DateStrip({ state, bundle, send, busy }: { state: ConversationState; bundle: Bundle; send: Send; busy: boolean }) {
    const [days, setDays] = useState<DateOption[] | null>(null);
    const plan = state.plan!;
    useEffect(() => {
        let alive = true;
        setDays(null);
        api.dates(state.id)
            .then((list) => alive && setDays(list))
            .catch(() => alive && setDays([]));
        return () => {
            alive = false;
        };
    }, [state.id, plan.checkin, bundle.id, bundle.total]);
    if (days && days.length === 0) return null;
    const better = days?.filter((d) => d.available && d.delta !== null && d.delta < 0).sort((a, b) => a.delta! - b.delta!)[0];
    return (
        <section className="card date-strip">
            <header>
                <h2>А если сдвинуть заезд?</h2>
                <span className="muted">{better ? `${day(better.date)} — дешевле на ${money(-better.delta!)}` : 'та же поездка, цена от двери до двери'}</span>
            </header>
            <div className="days" role="group" aria-label="Цена поездки по дням заезда" aria-busy={!days}>
                {(days ?? LOADING_DAYS).map((d) => {
                    const current = d.offset === 0;
                    const date = d.date ? new Date(`${d.date}T12:00:00`) : null;
                    const label = d.date ? `Заезд ${day(d.date)}` : '';
                    return (
                        <button
                            key={d.offset}
                            className={`dday${current ? ' current' : ''}${d.cheapest ? ' cheapest' : ''}`}
                            disabled={busy || !d.available || current}
                            aria-current={current ? 'date' : undefined}
                            aria-label={d.available ? `${label}: ${money(d.total!)}${current ? ', сейчас в плане' : ''}` : label || 'Загружаю'}
                            onClick={() => send({ action: { type: 'edit_brief', patch: { date_from: d.date, month: Number(d.date.slice(5, 7)) } } }, label)}
                        >
                            <small>{date ? WEEKDAYS[date.getDay()] : '…'}</small>
                            <b>{date ? date.getDate() : ''}</b>
                            {d.available ? (
                                <>
                                    <span className="dprice">{(d.total! / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} тыс</span>
                                    <span className={`ddelta ${d.delta! < 0 ? 'down' : d.delta! > 0 ? 'up' : ''}`}>
                                        <span className="dfull">{current ? 'сейчас' : signed(d.delta!)}</span>
                                        <span className="dshort" aria-hidden="true">
                                            {current ? 'сейчас' : `${d.delta! > 0 ? '+' : d.delta! < 0 ? '−' : ''}${(Math.abs(d.delta!) / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })}к`}
                                        </span>
                                    </span>
                                    {d.same_hotel === false && <span className="dnote">другой отель</span>}
                                </>
                            ) : (
                                <span className="dprice muted">{days ? 'нет мест' : ''}</span>
                            )}
                        </button>
                    );
                })}
            </div>
        </section>
    );
}

function DateScan({ plan }: { plan: Plan }) {
    if (plan.dates_how !== 'best_in_month' || plan.date_scan.length < 3) return null;
    const max = Math.max(...plan.date_scan.map((d) => d.estimate));
    const min = Math.min(...plan.date_scan.map((d) => d.estimate));
    return (
        <section className="card">
            <header>
                <h2>Цены по датам заезда</h2>
                <span className="muted">оценка поездки целиком — выбрал самую выгодную</span>
            </header>
            <div className="scan" role="img" aria-label="Оценка стоимости поездки по датам заезда">
                {plan.date_scan.map((d) => (
                    <div key={d.date} className={`bar ${d.date === plan.checkin ? 'best' : ''}`} title={`${day(d.date)}: ~${money(d.estimate)}`}>
                        <i style={{ height: `${25 + (75 * (d.estimate - min)) / Math.max(1, max - min)}%` }} />
                        <span>{Number(d.date.slice(8, 10))}</span>
                    </div>
                ))}
            </div>
        </section>
    );
}

export function TripHero({ bundle, people }: { bundle: Bundle; people?: string }) {
    const info = bundle.dest_info;
    const w = info?.weather;
    return (
        <section className="hero">
            <Cover dest={bundle.dest} seed={bundle.dest} kinds={info?.kinds ?? ['city']} air={w?.air} water={w?.water} rain={w?.rain} height={170} title={bundle.dest_name} />
            <div className="hero-text">
                <span className="hero-kicker">
                    {info?.country}
                    {info?.dynamic ? ' · найдено на карте' : ''}
                </span>
                <h2>{bundle.dest_name}</h2>
                <span>
                    {day(bundle.checkin)} – {day(bundle.checkout)} · {bundle.nights} ноч.{people ? ` · ${people}` : ''}
                </span>
                <div className="hero-chips">
                    {w?.air !== null && w?.air !== undefined && (
                        <span>
                            <Icon name="sun" size={14} /> днём {w.air > 0 ? '+' : ''}
                            {w.air}°
                        </span>
                    )}
                    {w?.water !== null && w?.water !== undefined && (
                        <span>
                            <Icon name="wave" size={14} /> вода +{w.water}°
                        </span>
                    )}
                    {w?.rain !== null && w?.rain !== undefined && (
                        <span>
                            <Icon name="umbrella" size={14} /> {w.rain} дн. с ливнями
                        </span>
                    )}
                    {info?.visa && (
                        <span>
                            <Icon name="passport" size={14} /> {info.visa.split(' — ')[0]}
                        </span>
                    )}
                </div>
            </div>
            <div className="hero-total">
                <small>«{bundle.label}»</small>
                <b>{money(bundle.total)}</b>
                <small>за всё, от двери до двери</small>
            </div>
        </section>
    );
}

function RouteView({ state, bundle, send, busy }: { state: ConversationState; bundle: Bundle; send: Send; busy: boolean }) {
    const legs = bundle.legs!;
    const party = state.chips.find((c) => c.key === 'party')?.label;
    return (
        <>
            <TripHero bundle={bundle} people={party} />
            {state.diff && <DiffBanner diff={state.diff} />}
            <section className="card">
                <header>
                    <h2>Маршрут: {bundle.dest_name}</h2>
                    <span className="muted">каждая часть — свой отель и трансферы, переезды проверены по времени</span>
                </header>
                <ol className="route">
                    {legs.map((leg, index) => (
                        <li key={leg.id}>
                            <span className="route-dot">{index + 1}</span>
                            <div>
                                <b>
                                    {leg.dest_name} · {leg.nights} ноч.
                                </b>
                                <span>
                                    {day(leg.checkin)} – {day(leg.checkout)} · {leg.hotel.name} {'★'.repeat(leg.hotel.stars)}, {leg.hotel.meal_label}
                                </span>
                                {index < legs.length - 1 && (
                                    <span className="route-hop">
                                        <Icon name={MODE_ICON[leg.inbound.mode] ?? 'car'} size={14} /> переезд {day(leg.inbound.depart)}: {transportLine(leg.inbound)}, {time(leg.inbound.depart)} → {time(leg.inbound.arrive)}, {duration(leg.inbound.duration_min)}
                                    </span>
                                )}
                            </div>
                            <span className="cost">{money(leg.total)}</span>
                        </li>
                    ))}
                </ol>
                <div className="route-total">
                    <span>Итого за маршрут, от двери до двери</span>
                    <b>{money(bundle.total)}</b>
                </div>
                {state.stage === 'plan' && (
                    <button className="primary big" disabled={busy} onClick={() => send({ action: { type: 'checkout' } }, 'Оформить')}>
                        Оформить маршрут за {money(bundle.total)}
                    </button>
                )}
            </section>
            {legs.map((leg, index) => (
                <Timeline key={leg.id} bundle={leg} send={send} busy={busy} title={`Часть ${index + 1}: ${leg.dest_name}`} />
            ))}
            <TripMap bundle={bundle} />
            <Priorities priorities={state.brief.priorities} busy={busy} onApply={(priorities) => send({ action: { type: 'set_priorities', priorities } }, 'Пересобрать по моим приоритетам')} />
        </>
    );
}

export default function PlanView({ state, send, busy }: { state: ConversationState; send: Send; busy: boolean }) {
    const plan = state.plan!;
    const bundle = plan.bundles[state.selected] ?? plan.bundles[0];
    const party = state.chips.find((c) => c.key === 'party')?.label;
    if (bundle.legs) return <RouteView state={state} bundle={bundle} send={send} busy={busy} />;
    // Иллюстрации отелей на экране плана: сначала карточки вариантов, потом строки отелей — ни одна не повторяется
    const pick = hotelPhotoPicker(plan.dest, bundle.dest_info?.kinds);
    const bundlePhotos = plan.bundles.map((b) => pick(b.hotel));
    const hotelPhotos = new Map(plan.hotels.map((h) => [h.id, pick(h)]));
    return (
        <>
            <TripHero bundle={bundle} people={party} />
            {state.diff && <DiffBanner diff={state.diff} />}
            <Caught bundle={bundle} />
            {plan.forecast && <ForecastCard forecast={plan.forecast} norm={bundle.dest_info?.weather.air} />}
            <section className="card">
                <header>
                    <h2>Варианты поездки</h2>
                    <span className="muted">цена «от двери до двери»: транспорт, отель, питание, трансферы</span>
                </header>
                <div className="bundles">
                    {plan.bundles.map((b, index) => (
                        <BundleCard key={b.id} bundle={b} selected={index === state.selected} busy={busy} photo={bundlePhotos[index]} onSelect={() => send({ action: { type: 'select_bundle', index } }, `Вариант «${b.label}»`)} />
                    ))}
                </div>
                {plan.bundles.length > 1 && <Compare bundles={plan.bundles} selected={state.selected} />}
                {state.stage === 'plan' && (
                    <button className="primary big" disabled={busy} onClick={() => send({ action: { type: 'checkout' } }, 'Оформить')}>
                        Оформить «{bundle.label}» за {money(bundle.total)}
                    </button>
                )}
            </section>
            {state.stage === 'plan' && plan.bundles.length > 1 && <GroupTrip state={state} send={send} busy={busy} />}
            {state.stage === 'plan' && <DateStrip state={state} bundle={bundle} send={send} busy={busy} />}
            {state.stage === 'plan' && <Hacks bundle={bundle} send={send} busy={busy} />}
            <Timeline bundle={bundle} send={send} busy={busy} />
            <TripMap bundle={bundle} />
            <Priorities priorities={state.brief.priorities} busy={busy} onApply={(priorities) => send({ action: { type: 'set_priorities', priorities } }, 'Пересобрать по моим приоритетам')} />
            <Alternatives plan={plan} bundle={bundle} send={send} busy={busy} photos={hotelPhotos} />
            <DateScan plan={plan} />
        </>
    );
}
