import { useEffect, useState } from 'react';
import { api, type QueueRow } from '../api';
import Brief from '../components/Brief';
import { TripHero } from '../components/PlanView';
import { money } from '../format';
import type { ConversationState } from '../types';
import '../components/Handoff.css';

const KEY = 'shturman.operator.key';
const NAME = 'shturman.operator.name';

function stored(key: string, fallback: string) {
    try {
        return localStorage.getItem(key) ?? fallback;
    } catch {
        return fallback;
    }
}

function keep(key: string, value: string) {
    try {
        localStorage.setItem(key, value);
    } catch {
        /* приватный режим: ключ проживёт до перезагрузки */
    }
}

function waited(since: number) {
    const minutes = Math.max(0, Math.round((Date.now() / 1000 - since) / 60));
    return minutes < 1 ? 'только что' : minutes < 60 ? `${minutes} мин` : `${Math.floor(minutes / 60)} ч ${minutes % 60} мин`;
}

// Консоль оператора: очередь обращений, которые агент передал людям, — с брифом, планом и следом агента
export default function OperatorPage() {
    const [key, setKey] = useState(() => stored(KEY, ''));
    const [draft, setDraft] = useState(key);
    const [name, setName] = useState(() => stored(NAME, ''));
    const [queue, setQueue] = useState<QueueRow[] | null>(null);
    const [selected, setSelected] = useState<string | null>(null);
    const [chat, setChat] = useState<ConversationState | null>(null);
    const [reply, setReply] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!key) return;
        const load = () =>
            api.operatorQueue(key)
                .then((rows) => {
                    setQueue(rows);
                    setError(null);
                })
                .catch((e: Error) => setError(e.message));
        void load();
        const timer = window.setInterval(load, 5000);
        return () => window.clearInterval(timer);
    }, [key]);

    useEffect(() => {
        if (!key || !selected) return;
        const load = () =>
            api.operatorConversation(key, selected)
                .then(setChat)
                .catch((e: Error) => setError(e.message));
        void load();
        const timer = window.setInterval(load, 4000);
        return () => window.clearInterval(timer);
    }, [key, selected]);

    const operator = name.trim() || 'Менеджер';
    const act = async (call: () => Promise<ConversationState>) => {
        setBusy(true);
        try {
            setChat(await call());
            setQueue(await api.operatorQueue(key));
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Не получилось');
        } finally {
            setBusy(false);
        }
    };

    if (!key) {
        return (
            <main className="page operator-page">
                <h1>Консоль оператора</h1>
                <section className="card">
                    <p>Обращения, которые агент передал людям: путешественник попросил менеджера или агент дважды не понял запрос.</p>
                    <form
                        className="operator-login"
                        onSubmit={(e) => {
                            e.preventDefault();
                            keep(KEY, draft.trim());
                            keep(NAME, name.trim());
                            setKey(draft.trim());
                        }}
                    >
                        <label>
                            Ключ оператора
                            <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="на демо-стенде: operator-demo" />
                        </label>
                        <label>
                            Ваше имя для путешественника
                            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Мария" />
                        </label>
                        <button className="primary" disabled={!draft.trim()}>
                            Открыть очередь
                        </button>
                    </form>
                </section>
            </main>
        );
    }

    const steps = (chat?.messages ?? []).flatMap((m) => m.steps ?? []);
    const bundle = chat?.plan?.bundles[chat.selected];
    const open = chat?.handoff && chat.handoff.status !== 'closed';
    return (
        <main className="page operator-page">
            <h1>Консоль оператора</h1>
            {error && <p className="error">{error}</p>}
            <div className="operator-grid">
                <section className="card">
                    <header>
                        <h2>Очередь</h2>
                        <span className="muted">{queue ? `${queue.length} в работе` : 'загружаю…'}</span>
                    </header>
                    {queue && queue.length === 0 && <p className="muted">Все обращения агент закрыл сам.</p>}
                    <ul className="operator-queue">
                        {(queue ?? []).map((row) => (
                            <li key={row.id} className={row.status}>
                                <button className={row.id === selected ? 'on' : ''} onClick={() => setSelected(row.id)}>
                                    <b>
                                        {row.trip ?? 'поездка ещё не собрана'} {row.unread > 0 && <span className="operator-unread">{row.unread}</span>}
                                    </b>
                                    <span>{row.last_message || row.reason}</span>
                                    <small>
                                        {row.status === 'waiting' ? `ждёт ${waited(row.since)}` : `на связи: ${row.operator}`} · {row.channel === 'telegram' ? 'Telegram' : 'сайт'} ·{' '}
                                        {row.reason}
                                    </small>
                                </button>
                            </li>
                        ))}
                    </ul>
                </section>
                <div className="operator-detail">
                    {!chat && <p className="muted">Выберите обращение слева: увидите, что человек хочет, собранный план и всё, что сделал агент.</p>}
                    {chat && (
                        <>
                            <Brief chips={chat.chips} busy onRemove={() => undefined} />
                            {bundle && (
                                <>
                                    <TripHero bundle={bundle} people={chat.chips.find((c) => c.key === 'party')?.label} />
                                    <p className="muted">
                                        Выбран «{bundle.label}»: {bundle.hotel.name} {'★'.repeat(bundle.hotel.stars)}, {bundle.hotel.meal_label}; туда {bundle.outbound.number}; итого{' '}
                                        {money(bundle.total)}. Этап: {chat.stage}.
                                    </p>
                                </>
                            )}
                            <section className="card">
                                <header>
                                    <h2>Что сделал агент</h2>
                                    <span className="muted">{steps.length} шагов</span>
                                </header>
                                <ol className="operator-trace">
                                    {steps.slice(-40).map((step, index) => (
                                        <li key={index}>
                                            <b>{step.title}</b> {step.detail && <span>— {step.detail}</span>}
                                        </li>
                                    ))}
                                </ol>
                            </section>
                            <section className="card">
                                <header>
                                    <h2>Диалог</h2>
                                    <span className="muted">{chat.handoff ? (chat.handoff.status === 'closed' ? 'обращение закрыто' : chat.handoff.reason) : ''}</span>
                                </header>
                                <div className="operator-chat">
                                    {chat.messages.map((m) => (
                                        <div key={m.id} className={`msg ${m.role} ${m.kind ?? ''}`}>
                                            {m.role === 'operator' && <span className="msg-author">{m.author}</span>}
                                            <div className="bubble">{m.text}</div>
                                        </div>
                                    ))}
                                </div>
                                {open && (
                                    <form
                                        className="operator-reply"
                                        onSubmit={(e) => {
                                            e.preventDefault();
                                            const text = reply.trim();
                                            if (!text) return;
                                            setReply('');
                                            void act(() => api.operatorReply(key, chat.id, text, operator));
                                        }}
                                    >
                                        <textarea value={reply} onChange={(e) => setReply(e.target.value)} placeholder={`Ответ от имени «${operator}»…`} aria-label="Ответ путешественнику" />
                                        <div className="actions">
                                            <button className="primary" disabled={busy || !reply.trim()}>
                                                Ответить
                                            </button>
                                            <button type="button" className="ghost" disabled={busy} onClick={() => void act(() => api.operatorClose(key, chat.id, operator))}>
                                                Вернуть агенту
                                            </button>
                                        </div>
                                    </form>
                                )}
                            </section>
                        </>
                    )}
                </div>
            </div>
        </main>
    );
}
