import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import Cover, { HotelPhoto, hotelPhotoPicker } from '../components/Cover';
import { day, money } from '../format';
import type { Booking } from '../types';

export default function TripsPage() {
    const [items, setItems] = useState<Booking[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        api.bookings()
            .then(setItems)
            .catch((e: Error) => setError(e.message));
    }, []);
    const shown = new Set<string>();
    const pickHotel = hotelPhotoPicker('trips');
    return (
        <main className="page">
            <h1>Мои поездки</h1>
            {error && <p className="error">{error}</p>}
            {items && !items.length && (
                <p className="muted">
                    Пока пусто. <Link to="/">Соберите первую поездку</Link> — это одно сообщение. Или <Link to="/login">войдите тестовым пользователем</Link>: у них уже есть покупки.
                </p>
            )}
            <div className="trips">
                {items?.map((b) => {
                    const info = b.bundle.dest_info;
                    // повторная поездка в то же место — не то же фото города, а свободная иллюстрация отеля
                    const repeat = shown.has(b.bundle.dest);
                    shown.add(b.bundle.dest);
                    return (
                        <Link key={b.id} to={`/trips/${b.id}`} className={`trip ${b.status}`}>
                            {repeat ? (
                                <HotelPhoto photo={pickHotel(b.bundle.hotel, info?.kinds)} height={170} />
                            ) : (
                                <Cover dest={b.bundle.dest} credit="text" seed={b.id} kinds={info?.kinds ?? ['city']} air={info?.weather.air} water={info?.weather.water} rain={info?.weather.rain} height={170} title={b.bundle.dest_name} />
                            )}
                            <h2>{b.bundle.dest_name}</h2>
                            <p>
                                {day(b.bundle.checkin)} – {day(b.bundle.checkout)} · {b.bundle.hotel.name}
                            </p>
                            <p className="trip-meta">
                                <span className={`status ${b.status}`}>{b.status === 'cancelled' ? 'отменена' : 'оформлена'}</span>
                                <b>{money(b.payment.amount)}</b>
                            </p>
                            <p className="muted small">{b.id}</p>
                        </Link>
                    );
                })}
            </div>
        </main>
    );
}
