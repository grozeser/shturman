import { useEffect, useState } from 'react';
import { api, type HotelReport, type HotelRow } from '../api';

const SEGMENT_LABELS: Record<string, string> = {
    family: 'Семьи с детьми',
    couple: 'Пары',
    solo: 'Соло',
    pets: 'С питомцем',
    seniors: 'Старшее поколение',
    party: 'Ночная жизнь',
    accessible: 'На коляске',
};

const FEATURE_LABELS: Record<string, string> = {
    kids_club: 'детский клуб',
    kids_pool: 'детский бассейн',
    family_rooms: 'семейные номера',
    pets: 'можно с животными',
    pool: 'бассейн',
    spa: 'спа',
    adults_only: 'только 16+',
    party: 'вечеринки',
    quiet: 'тихий',
    early_checkin: 'ранний заезд',
    late_checkout: 'поздний выезд',
    accessible: 'доступная среда',
};

function heat(score: number) {
    if (score === 0) return '#fbdede';
    // фирменный цвет: чем гуще, тем лучше подходит; фон всегда светлый — тёмный текст читается и в тёмной теме
    return `color-mix(in srgb, #5cc2bd ${Math.round(15 + score * 0.85)}%, #effaf9)`;
}

function Report({ id }: { id: string }) {
    const [report, setReport] = useState<HotelReport | null>(null);
    useEffect(() => {
        setReport(null);
        api.hotel(id).then(setReport).catch(() => setReport(null));
    }, [id]);
    if (!report) return <section className="card loading">Считаю…</section>;
    const h = report.hotel;
    const stats = report.stats;
    const reasons = Object.entries(stats.reasons).sort((a, b) => b[1] - a[1]);
    return (
        <section className="card hotel-report">
            <header>
                <h2>
                    {h.name} <span className="stars">{'★'.repeat(h.stars)}</span> <span className="rating">{h.rating.toFixed(1).replace('.', ',')}</span>
                </h2>
                <span className="muted">
                    {h.dest_name}, {h.area}
                    {h.beach_m !== null ? ` · ${h.beach_m} м до моря` : ''}
                </span>
            </header>
            <div className="feature-tags">
                {Object.entries(h.features)
                    .filter(([, on]) => on)
                    .map(([key]) => (
                        <span key={key}>{FEATURE_LABELS[key] ?? key}</span>
                    ))}
            </div>

            <h3 className="sub">Кому агент вас рекомендует</h3>
            <p className="muted small">Пригодность для типовых гостей — тем же расчётом, что и при подборе. 0 — таким гостям агент вас не покажет.</p>
            <ul className="segments">
                {Object.entries(report.segments).map(([key, s]) => (
                    <li key={key}>
                        <span className="seg-name">{s.label}</span>
                        <span className="seg-score" style={{ background: heat(s.score) }}>
                            {s.score}
                        </span>
                        <span className="muted">{s.excluded ? `не покажем: ${s.excluded}` : [...s.pros.slice(0, 2), ...s.cons.slice(0, 1).map((c) => `− ${c}`)].join(' · ')}</span>
                    </li>
                ))}
            </ul>
            {report.best_for.length > 0 && (
                <p>
                    <b>Ваши гости:</b> {report.best_for.join(', ')}. Им агент показывает вас в первую очередь — меньше разочарований и отмен.
                </p>
            )}

            <h3 className="sub">Что изменить, чтобы приходили «свои»</h3>
            {report.improvements.length ? (
                <ul className="ideas">
                    {report.improvements.map((idea) => (
                        <li key={idea.feature}>
                            <b>{idea.title[0].toUpperCase() + idea.title.slice(1)}</b>
                            <span>
                                {Object.entries(idea.gains)
                                    .map(([seg, gain]) => `${seg} +${gain}`)
                                    .join(', ')}
                                {idea.opens.length ? ` · откроет сегмент: ${idea.opens.join(', ')}` : ''}
                            </span>
                        </li>
                    ))}
                </ul>
            ) : (
                <p className="muted">Значимых улучшений нет — отель уже хорошо закрывает свои сегменты.</p>
            )}

            <h3 className="sub">Живая статистика агента</h3>
            <div className="kpis">
                <div className="kpi">
                    <b>{stats.recommended}</b>
                    <span>Раз рекомендован в варианте поездки</span>
                </div>
                <div className="kpi">
                    <b>{stats.rejected}</b>
                    <span>Раз отсеян — не отправили неподходящих гостей</span>
                </div>
                <div className="kpi">
                    <b>{stats.booked}</b>
                    <span>Броней</span>
                </div>
            </div>
            {Object.keys(stats.segments).length > 0 && (
                <p className="muted">Кому показывали: {Object.entries(stats.segments).map(([seg, n]) => `${SEGMENT_LABELS[seg] ?? seg} — ${n}`).join(', ')}</p>
            )}
            {reasons.length > 0 && <p className="muted">Почему отсеивали: {reasons.map(([reason, n]) => `${reason} — ${n}`).join('; ')}</p>}
        </section>
    );
}

export default function HotelsPage() {
    const [destinations, setDestinations] = useState<{ id: string; name: string; country: string }[]>([]);
    const [dest, setDest] = useState('antalya');
    const [rows, setRows] = useState<HotelRow[] | null>(null);
    const [selected, setSelected] = useState<string | null>(null);
    useEffect(() => {
        api.destinations().then(setDestinations).catch(() => setDestinations([]));
    }, []);
    useEffect(() => {
        setRows(null);
        api.hotels(dest)
            .then((list) => {
                setRows(list);
                setSelected(list[0]?.id ?? null);
            })
            .catch(() => setRows([]));
    }, [dest]);
    return (
        <main className="page wide">
            <h1>Для отеля</h1>
            <p className="muted">
                Агент рекомендует отель тем гостям, которым он действительно подходит, и объясняет почему. Здесь видно, для кого вы «свой», кому агент вас не покажет и что изменить, чтобы
                приходили нужные гости. Данные отелей синтетические.
            </p>
            <label className="dest-select">
                Направление
                <select value={dest} onChange={(e) => setDest(e.target.value)}>
                    {destinations.map((d) => (
                        <option key={d.id} value={d.id}>
                            {d.name} — {d.country}
                        </option>
                    ))}
                </select>
            </label>
            <div className="hotels-layout">
                <section className="card">
                    <table className="compare heat">
                        <thead>
                            <tr>
                                <th>Отель</th>
                                {Object.values(SEGMENT_LABELS).map((label) => (
                                    <th key={label}>{label}</th>
                                ))}
                                <th>Рекоменд.</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows?.map((row) => (
                                <tr key={row.id} className={row.id === selected ? 'sel' : ''} onClick={() => setSelected(row.id)}>
                                    <th>
                                        {row.name} <span className="stars">{'★'.repeat(row.stars)}</span>
                                    </th>
                                    {Object.keys(SEGMENT_LABELS).map((seg) => (
                                        <td key={seg} style={{ background: heat(row.segments[seg] ?? 0) }}>
                                            {row.segments[seg] || '—'}
                                        </td>
                                    ))}
                                    <td>{row.recommended}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </section>
                {selected && <Report id={selected} />}
            </div>
        </main>
    );
}
