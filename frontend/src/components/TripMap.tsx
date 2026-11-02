import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useEffect, useRef, useState } from 'react';
import type { Bundle } from '../types';
import './TripMap.css';

type View = 'place' | 'road';

const escape = (text: string) => text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

function pin(className: string, label: string) {
    // свои значки из CSS: стандартная картинка-маркер Leaflet теряется при сборке Vite;
    // якорь в точке, центрирует сам значок через translate(-50%, -50%) — ширина у подписей разная
    return L.divIcon({ className: '', html: `<span class="map-pin ${className}">${label}</span>`, iconSize: undefined, iconAnchor: [0, 0] });
}

/**
 * Карта поездки: откуда летим, куда и по какому маршруту. Только реальная география — город вылета и города поездки.
 * Отели в демо синтетические, поэтому отдельной точкой их не ставим (оказались бы и в море), а подписываем у города.
 * Подложка — OpenStreetMap; без интернета точки и линии всё равно видны.
 */
export default function TripMap({ bundle }: { bundle: Bundle }) {
    const box = useRef<HTMLDivElement>(null);
    const map = useRef<L.Map | null>(null);
    const bounds = useRef<Record<View, L.LatLngBounds> | null>(null);
    const [view, setView] = useState<View>('road');
    const stays = bundle.legs ?? [bundle];
    const origin = bundle.dest_info?.origin;
    const located = stays.every((s) => s.dest_info?.lat !== undefined && s.dest_info?.lon !== undefined);

    useEffect(() => {
        if (!box.current || !located) return;
        const m = L.map(box.current, { scrollWheelZoom: false });
        map.current = m;
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 18,
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(m);
        const places: L.LatLngTuple[] = stays.map((s) => [s.dest_info!.lat!, s.dest_info!.lon!]);
        const road: L.LatLngTuple[] = origin ? [[origin.lat, origin.lon], ...places, [origin.lat, origin.lon]] : places;
        L.polyline(road, { className: 'map-road', weight: 2.5, dashArray: '6 8' }).addTo(m);
        if (origin) L.marker([origin.lat, origin.lon], { icon: pin('origin', escape(origin.name)), keyboard: false }).addTo(m);
        stays.forEach((stay, index) => {
            const number = stays.length > 1 ? `${index + 1}. ` : '';
            const label = `<b>${number}${escape(stay.dest_name)}</b><small>★ ${escape(stay.hotel.name)} · ${stay.nights} ноч.</small>`;
            L.marker(places[index], { icon: pin('chosen', label), title: `${stay.dest_name}: ${stay.hotel.name}` }).addTo(m);
        });
        bounds.current = { road: L.latLngBounds(road), place: L.latLngBounds(places) };
        m.fitBounds(bounds.current.road, { padding: [48, 48], maxZoom: 10 });
        setView('road');
        return () => {
            m.remove();
            map.current = null;
        };
    }, [bundle.id, located]); // карту пересобираем, только когда меняется сама поездка

    const show = (next: View) => {
        setView(next);
        if (map.current && bounds.current) map.current.fitBounds(bounds.current[next], { padding: [48, 48], maxZoom: next === 'place' ? 11 : 10 });
    };

    if (!located) return null;
    return (
        <section className="card trip-map">
            <header>
                <h2>Поездка на карте</h2>
                <div className="map-views" role="group" aria-label="Масштаб карты">
                    <button className={view === 'road' ? 'on' : ''} aria-pressed={view === 'road'} onClick={() => show('road')}>
                        Вся дорога
                    </button>
                    <button className={view === 'place' ? 'on' : ''} aria-pressed={view === 'place'} onClick={() => show('place')}>
                        {stays.length > 1 ? 'Маршрут' : 'На месте'}
                    </button>
                </div>
            </header>
            <div
                ref={box}
                className="map-box"
                role="img"
                aria-label={`Карта: ${origin ? `из ${origin.name} — ` : ''}${stays.map((s) => `${s.dest_name}, отель ${s.hotel.name}`).join(' → ')}`}
            />
            <p className="muted small">Линия — дорога туда и обратно. Отели в демо синтетические, поэтому подписаны у города, а не точкой на улице.</p>
        </section>
    );
}
