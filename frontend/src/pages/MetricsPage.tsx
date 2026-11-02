import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type Metrics } from '../api';
import { money } from '../format';

const LIVE_LABELS: Record<string, string> = {
    conversations: 'Диалогов',
    reached_recommendation: 'Дошли до рекомендации',
    booked: 'Оформлено поездок',
    avg_clarifications: 'Уточнений на диалог',
    median_turns_to_first_rec: 'Ходов до первой рекомендации (медиана)',
    replans: 'Пересборок плана',
    llm_calls: 'Вызовов LLM',
    llm_fallbacks: 'Фолбэков на правила',
    number_violations_blocked: 'Ответов LLM отброшено за выдуманные числа',
    handoffs: 'Передано менеджерам',
    handoff_share: 'Доля обращений у людей (остальные агент закрыл сам)',
};

const EVAL_LABELS: Record<string, string> = {
    cases: 'Сценариев',
    completed_rate: 'Доведено до оплаты',
    avg_clarifications: 'Уточнений в среднем',
    max_clarifications: 'Максимум уточнений',
    avg_turns_to_first_rec: 'Ходов до первой рекомендации',
    median_ms_to_first_rec: 'Время до первой рекомендации, мс (в режиме прогона; с LLM на CPU — десятки секунд)',
    connection_errors: 'Ошибок стыковок в итоговом плане',
    constraint_violations: 'Нарушений ограничений',
    field_accuracy: 'Точность разбора запроса',
    replan_kept_rate: 'Пересборок без смены отеля',
};

function show(value: number | string | null | undefined, key: string) {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'number' && (key.endsWith('rate') || key.endsWith('share') || key === 'field_accuracy')) return `${Math.round(value * 100)}%`;
    return String(value);
}

function Business({ data }: { data: Metrics['business'] }) {
    const top = Math.max(1, data.funnel[0]?.count ?? 1);
    const pct = (v: number | null) => (v === null ? '—' : `${Math.round(v * 100)}%`);
    return (
        <section className="card">
            <header>
                <h2>Для бизнеса: путь от идеи до покупки</h2>
                <span className="muted">живые данные этого стенда, включая поездки тестовых пользователей</span>
            </header>
            <div className="funnel">
                {data.funnel.map((row, index) => (
                    <div key={row.step} className="funnel-row">
                        <span>{row.step}</span>
                        <div className="funnel-bar">
                            <i style={{ width: `${Math.max(2, (row.count / top) * 100)}%` }} />
                        </div>
                        <b>{row.count}</b>
                        <small>{index ? `${Math.round((row.count / Math.max(1, data.funnel[index - 1].count)) * 100)}% от шага выше` : ''}</small>
                    </div>
                ))}
            </div>
            <div className="kpis">
                <div className="kpi">
                    <b>{data.avg_check ? money(data.avg_check) : '—'}</b>
                    <span>Средний чек: поездка целиком, а не только отель</span>
                </div>
                <div className="kpi">
                    <b>{pct(data.package_share)}</b>
                    <span>Броней с дорогой и трансфером: агент всегда собирает поездку целиком, а не только отель</span>
                </div>
                <div className="kpi">
                    <b>{pct(data.upsell_share)}</b>
                    <span>С допродажей: питание, индивидуальный трансфер, ранний заезд, страховка</span>
                </div>
                <div className="kpi">
                    <b>{pct(data.insurance_share ?? null)}</b>
                    <span>Броней со страховкой: полис одной галочкой в корзине</span>
                </div>
                <div className="kpi">
                    <b>{data.post_purchase_actions}</b>
                    <span>Действий после покупки (ранний заезд, перенос, трансфер)</span>
                </div>
                <div className="kpi">
                    <b>{data.avg_minutes_saved ? `≈ ${data.avg_minutes_saved} мин` : '—'}</b>
                    <span>
                        Сэкономлено на бронь
                        {data.avg_messages && data.avg_clicks_saved ? `: ${String(data.avg_messages).replace('.', ',')} шага в чате вместо ~${data.avg_clicks_saved} кликов` : ''}
                    </span>
                </div>
            </div>
        </section>
    );
}

export default function MetricsPage() {
    const [data, setData] = useState<Metrics | null>(null);
    useEffect(() => {
        api.metrics()
            .then(setData)
            .catch(() => setData(null));
    }, []);
    if (!data) return <main className="page loading">Загружаю метрики…</main>;
    return (
        <main className="page">
            <h1>Метрики качества агента</h1>
            <Business data={data.business} />
            {data.eval ? (
                <section className="card">
                    <header>
                        <h2>Эталонный прогон</h2>
                        <span className="muted">
                            {data.eval.mode} · {new Date(data.eval.generated).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}
                        </span>
                    </header>
                    <div className="kpis">
                        {Object.entries(data.eval.summary).map(([key, value]) => (
                            <div key={key} className="kpi">
                                <b>{show(value, key)}</b>
                                <span>{EVAL_LABELS[key] ?? key}</span>
                            </div>
                        ))}
                    </div>
                    <table className="compare">
                        <thead>
                            <tr>
                                <th>Запрос</th>
                                <th>Итог</th>
                                <th>Ходов</th>
                                <th>Уточнений</th>
                                <th>Замечания</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.eval.cases.map((c) => (
                                <tr key={c.id}>
                                    <td>{c.text}</td>
                                    <td>{c.ok ? '✓' : '✕'}</td>
                                    <td>{c.turns}</td>
                                    <td>{c.clarifications}</td>
                                    <td className="muted">{c.problems.join('; ')}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </section>
            ) : (
                <p className="muted">Эталонный прогон ещё не запускали: python -m app.eval</p>
            )}
            <section className="card">
                <header>
                    <h2>Живые показатели стенда</h2>
                    <span className="muted">
                        по всем диалогам в базе · <Link to="/operator">консоль оператора</Link>
                    </span>
                </header>
                <div className="kpis">
                    {Object.entries(data.live).map(([key, value]) => (
                        <div key={key} className="kpi">
                            <b>{show(value, key)}</b>
                            <span>{LIVE_LABELS[key] ?? key}</span>
                        </div>
                    ))}
                </div>
            </section>
        </main>
    );
}
