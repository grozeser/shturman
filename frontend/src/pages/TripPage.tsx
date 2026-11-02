import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api';
import { day, duration, money, time } from '../format';
import Cover from '../components/Cover';
import Savings from '../components/Savings';
import TripMap from '../components/TripMap';
import ForecastCard from '../components/ForecastCard';
import type { Booking } from '../types';
import './TripPage.css';

// Отметки «уже положил» — удобство одного браузера, поэтому localStorage; без него список просто не запоминается
function Checklist({ id, groups }: { id: string; groups: NonNullable<Booking['checklist']> }) {
    const key = `shturman.packed.${id}`;
    const [packed, setPacked] = useState<string[]>(() => {
        try {
            return JSON.parse(localStorage.getItem(key) ?? '[]');
        } catch {
            return [];
        }
    });
    const toggle = (text: string) => {
        const next = packed.includes(text) ? packed.filter((t) => t !== text) : [...packed, text];
        setPacked(next);
        try {
            localStorage.setItem(key, JSON.stringify(next));
        } catch {
            /* приватный режим: отметки живут до перезагрузки */
        }
    };
    const total = groups.reduce((n, g) => n + g.items.length, 0);
    return (
        <section className="card checklist">
            <header>
                <h2>Что взять с собой</h2>
                <span className="muted">
                    собрал по погоде, составу и визе · готово {packed.length} из {total}
                </span>
            </header>
            <div className="checklist-groups">
                {groups
                    .filter((g) => g.items.length)
                    .map((group) => (
                        <div key={group.title}>
                            <h3 className="sub">{group.title}</h3>
                            <ul>
                                {group.items.map((item) => (
                                    <li key={item.text}>
                                        <label className={packed.includes(item.text) ? 'done' : ''}>
                                            <input type="checkbox" checked={packed.includes(item.text)} onChange={() => toggle(item.text)} />
                                            <span>
                                                {item.text}
                                                {item.why && <small>{item.why}</small>}
                                            </span>
                                        </label>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    ))}
            </div>
        </section>
    );
}

export default function TripPage() {
    const { id } = useParams();
    const [booking, setBooking] = useState<Booking | null>(null);
    const [answer, setAnswer] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        if (id)
            api.booking(id)
                .then(setBooking)
                .catch((e: Error) => setError(e.message));
    }, [id]);
    if (error) return <main className="page error">{error}</main>;
    if (!booking) return <main className="page loading">Загружаю поездку…</main>;
    const b = booking.bundle;
    const act = async (post: Record<string, unknown>) => {
        setBusy(true);
        try {
            const result = await api.bookingAction(booking.id, post);
            setBooking(result.booking);
            setAnswer(result.text);
        } catch (e) {
            setAnswer(e instanceof Error ? e.message : 'Не получилось');
        } finally {
            setBusy(false);
        }
    };
    const cancelled = booking.status === 'cancelled';
    return (
        <main className="page trip-page">
            <p>
                <Link to="/trips">← Мои поездки</Link>
            </p>
            <div className="voucher card ticket">
                <Cover dest={b.dest} seed={b.dest} kinds={b.dest_info?.kinds ?? ['city']} air={b.dest_info?.weather.air} water={b.dest_info?.weather.water} rain={b.dest_info?.weather.rain} height={130} title={b.dest_name} />
                <header>
                    <div>
                        <h1>{b.dest_name}</h1>
                        <p>
                            {day(b.checkin)} – {day(b.checkout)} · {b.nights} ноч. · {booking.traveller.name}
                        </p>
                    </div>
                    <div className="code">
                        <small>бронь</small>
                        <b>{booking.id}</b>
                        <span className={`status ${booking.status}`}>{cancelled ? 'отменена' : 'подтверждена'}</span>
                    </div>
                </header>
                <div className="perf" aria-hidden="true" />
                <div className="voucher-grid">
                    <div>
                        <h3>Туда</h3>
                        <p>
                            {b.outbound.number}, {day(b.outbound.depart)} {time(b.outbound.depart)} → {time(b.outbound.arrive)}
                            <br />
                            {b.outbound.from} → {b.outbound.to}, {duration(b.outbound.duration_min)}
                        </p>
                    </div>
                    <div>
                        <h3>Отель</h3>
                        <p>
                            {b.hotel.name} {'★'.repeat(b.hotel.stars)}
                            <br />
                            {b.hotel.meal_label}, заселение с {b.hotel.checkin}, выезд до {b.hotel.checkout}
                        </p>
                    </div>
                    <div>
                        <h3>Трансфер</h3>
                        <p>{b.transfer_in.title}</p>
                    </div>
                    <div>
                        <h3>Обратно</h3>
                        <p>
                            {b.inbound.number}, {day(b.inbound.depart)} {time(b.inbound.depart)} → {time(b.inbound.arrive)}
                        </p>
                    </div>
                    {booking.insurance && (
                        <div>
                            <h3>Страховка</h3>
                            <p>
                                Полис {booking.insurance.number}, покрытие {booking.insurance.coverage}
                                <br />
                                {booking.insurance.includes.join(', ')}
                            </p>
                        </div>
                    )}
                </div>
                {booking.passport && !booking.passport.ok && <p className="error">{booking.passport.text}</p>}
                {b.legs && (
                    <ol className="route">
                        {b.legs.map((leg, index) => (
                            <li key={leg.id}>
                                <span className="route-dot">{index + 1}</span>
                                <div>
                                    <b>
                                        {leg.dest_name} · {day(leg.checkin)} – {day(leg.checkout)}
                                    </b>
                                    <span>
                                        {leg.hotel.name} {'★'.repeat(leg.hotel.stars)}, {leg.hotel.meal_label}
                                        {index < b.legs!.length - 1 ? ` · переезд ${time(leg.inbound.depart)} → ${time(leg.inbound.arrive)}` : ''}
                                    </span>
                                </div>
                            </li>
                        ))}
                    </ol>
                )}
                {(b.extras.length > 0 || booking.services.length > 0) && (
                    <p className="extras">
                        {[...b.extras.map((e) => e.title), ...booking.services.map((s) => `${s.title}${s.status === 'waitlist' ? ' (ожидание)' : ''}`)].join(' · ')}
                    </p>
                )}
                {booking.requests && booking.requests.length > 0 && (
                    <p className="extras requests">Заранее предупредил: {booking.requests.map((r) => `${r.who} — ${r.what}`).join('; ')}</p>
                )}
                <footer>
                    <span>
                        Оплачено {money(booking.payment.amount)} · {booking.payment.method}
                        {booking.payment.refund ? ` · возврат ${money(booking.payment.refund)}` : ''}
                    </span>
                    <span className="voucher-actions">
                        <button className="ghost" onClick={() => api.calendarFile(booking.id).catch((e: Error) => setAnswer(e.message))}>
                            Добавить в календарь
                        </button>
                        <button className="ghost" onClick={() => window.print()}>
                            Распечатать ваучер
                        </button>
                    </span>
                </footer>
            </div>

            {!cancelled && (
                <section className="card">
                    <h2>Агент после покупки</h2>
                    <div className="actions">
                        <button disabled={busy} onClick={() => act({ type: 'early_checkin' })}>
                            Ранний заезд
                        </button>
                        <button disabled={busy} onClick={() => act({ type: 'late_checkout' })}>
                            Поздний выезд
                        </button>
                        <button disabled={busy} onClick={() => act({ type: 'add_transfer' })}>
                            Индивидуальный трансфер
                        </button>
                        <button disabled={busy} onClick={() => act({ type: 'change_dates', shift_days: 2 })}>
                            Перенести на 2 дня позже
                        </button>
                        <button disabled={busy} onClick={() => act({ type: 'change_dates', shift_days: -2 })}>
                            На 2 дня раньше
                        </button>
                        <button disabled={busy} className="danger" onClick={() => act({ type: 'cancel' })}>
                            Отменить поездку
                        </button>
                    </div>
                    <div className="plan-b">
                        <p className="muted small">
                            <b>План Б.</b> Что агент сделает, если что-то сорвётся, — симуляция: ничего не меняется, пока вы не подтвердите.
                        </p>
                        <div className="actions">
                            <button disabled={busy} onClick={() => act({ type: 'disruption', what: 'flight_cancelled' })}>
                                Если отменят рейс туда
                            </button>
                            <button disabled={busy} onClick={() => act({ type: 'disruption', what: 'hotel_overbooked' })}>
                                Если отель не заселит
                            </button>
                        </div>
                    </div>
                    {answer && <p className="answer">{answer}</p>}
                    {booking.pending && (
                        <div className="actions">
                            <button className="primary" disabled={busy} onClick={() => act({ type: 'confirm' })}>
                                Подтвердить
                            </button>
                            <button disabled={busy} onClick={() => act({ type: 'decline' })}>
                                Оставить как есть
                            </button>
                        </div>
                    )}
                </section>
            )}

            {booking.savings && <Savings savings={booking.savings} compact />}
            {!cancelled && <TripMap bundle={b} />}
            {!cancelled && booking.forecast && <ForecastCard forecast={booking.forecast} norm={b.dest_info?.weather.air} />}
            {!cancelled && booking.checklist && <Checklist id={booking.id} groups={booking.checklist} />}

            <div className="two">
                <section className="card">
                    <h2>Напоминания</h2>
                    <p className="muted small">Если оформляли поездку в Telegram-боте, они придут туда сами, в нужное время.</p>
                    <ul className="reminders">
                        {booking.reminders.map((r) => (
                            <li key={r.at + r.text}>
                                <time>
                                    {day(r.at)}, {time(r.at)}
                                </time>
                                {r.text}
                            </li>
                        ))}
                    </ul>
                </section>
                <section className="card">
                    <h2>История</h2>
                    <ul className="reminders">
                        {booking.history.map((h) => (
                            <li key={h.ts + h.text}>
                                <time>
                                    {day(h.ts)}, {time(h.ts)}
                                </time>
                                {h.text}
                            </li>
                        ))}
                    </ul>
                </section>
            </div>
        </main>
    );
}
