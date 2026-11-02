import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import Brief from '../components/Brief';
import Chat from '../components/Chat';
import Checkout from '../components/Checkout';
import Comparison from '../components/Comparison';
import Destinations from '../components/Destinations';
import HandoffBanner from '../components/HandoffBanner';
import Icon, { type IconName } from '../components/Icon';
import PlanView, { TripHero } from '../components/PlanView';
import Cover from '../components/Cover';
import Savings from '../components/Savings';
import type { SceneProps } from '../components/Scene';
import { useAccount } from '../useAccount';
import { useAgent } from '../useAgent';

// Промо-карточки: кикер — место на фото, заголовок — тип отдыха
const WELCOME: (SceneProps & { dest: string; kicker: string })[] = [
    { dest: 'maldives', seed: 'welcome-sea', kinds: ['sea', 'exotic'], air: 29, water: 27, title: 'Тёплое море', kicker: 'Мальдивы' },
    { dest: 'krasnaya_polyana', seed: 'welcome-mountains', kinds: ['ski'], air: -4, title: 'Горы', kicker: 'Красная Поляна' },
    { dest: 'spb', seed: 'welcome-city', kinds: ['city'], air: 18, title: 'Город', kicker: 'Санкт-Петербург' },
];

const FEATURES: [IconName, string][] = [
    ['compass', 'Направления с погодой, дорогой и ценой'],
    ['suitcase', 'Три собранных варианта «от двери до двери»'],
    ['check', 'Проверка: прилёт → трансфер → заселение'],
    ['refresh', '«А если на 2 дня позже?» — пересборка с diff'],
];

export default function AgentPage() {
    const { state, setState, busy, liveSteps, thinking, pendingUser, error, send, restart } = useAgent();
    const [tab, setTab] = useState<'chat' | 'plan'>('chat');
    const canvas = useRef<HTMLElement>(null);
    const account = useAccount();
    const planKey = `${state?.stage}-${state?.plan?.dest}-${state?.suggestions?.items[0]?.id}`;
    useEffect(() => {
        canvas.current?.scrollTo({ top: 0, behavior: 'smooth' });
    }, [planKey]);

    if (!state) {
        return <main className="loading">{error ? `Не удалось подключиться к агенту: ${error}` : 'Подключаюсь к агенту…'}</main>;
    }
    const plan = state.plan;
    const bundle = plan?.bundles[state.selected];
    const hasCanvas = Boolean(state.suggestions || plan || state.comparison || state.chips.some((c) => c.kind !== 'default'));
    return (
        <main className={`agent-page tab-${tab}`}>
            <nav className="mobile-tabs" aria-label="Чат или план">
                <button className={tab === 'chat' ? 'on' : ''} onClick={() => setTab('chat')} aria-pressed={tab === 'chat'}>
                    <Icon name="chat" size={18} />
                    Чат
                </button>
                <button className={tab === 'plan' ? 'on' : ''} onClick={() => setTab('plan')} aria-pressed={tab === 'plan'}>
                    <Icon name="map" size={18} />
                    План{plan ? ` · ${plan.bundles.length}` : state.suggestions ? ` · ${state.suggestions.items.length}` : ''}
                </button>
            </nav>
            <section className="chat-pane">
                <div className="pane-head">
                    <h1>Диалог</h1>
                    <button className="ghost" onClick={() => void restart()} disabled={busy}>
                        Новая поездка
                    </button>
                </div>
                {state.handoff && state.handoff.status !== 'closed' && <HandoffBanner handoff={state.handoff} send={send} busy={busy} />}
                <Chat messages={state.messages} busy={busy} liveSteps={liveSteps} thinking={thinking} pendingUser={pendingUser} onSend={send} />
                {error && <p className="error">{error}</p>}
            </section>
            <section className="canvas" aria-label="План поездки" ref={canvas}>
                {!hasCanvas && (
                    <div className="empty">
                        <h2>Скажите, куда хотите отправиться. Остальное устрою я!</h2>
                        <p>Опишите, чего хочется, как написали бы другу. Агент сам уточнит главное, подберёт направление, соберёт перелёт, отель и трансфер, проверит стыковки и объяснит выбор.</p>
                        <div className="empty-art">
                            {WELCOME.map(({ kicker, ...scene }) => (
                                <figure key={scene.seed} className="promo">
                                    <Cover {...scene} height={180} />
                                    <figcaption>
                                        <span>{kicker}</span>
                                        <b>{scene.title}</b>
                                    </figcaption>
                                </figure>
                            ))}
                        </div>
                        <ul>
                            {FEATURES.map(([icon, text]) => (
                                <li key={text}>
                                    <Icon name={icon} />
                                    {text}
                                </li>
                            ))}
                        </ul>
                        {account === null && (
                            <p className="empty-login">
                                Хотите сразу посмотреть готовые поездки? <Link to="/login">Войдите тестовым пользователем</Link> — у них уже есть покупки, память и
                                действия после покупки.
                            </p>
                        )}
                    </div>
                )}
                {hasCanvas && <Brief chips={state.chips} busy={busy} onRemove={(chip) => send({ action: { type: 'remove_chip', key: chip.key } }, `Убрать: ${chip.label}`)} />}
                {state.stage === 'booked' && bundle && <TripHero bundle={bundle} />}
                {state.stage === 'booked' && state.booking_id && (
                    <section className="card booked-card ticket">
                        <h2>Поездка оформлена</h2>
                        <div className="perf" aria-hidden="true" />
                        <p>
                            Бронь <b>{state.booking_id}</b>. Ранний заезд, перенос дат, трансфер — пишите в чат или откройте поездку.
                        </p>
                        <Link className="button primary" to={`/trips/${state.booking_id}`}>
                            Открыть поездку
                        </Link>
                    </section>
                )}
                {state.stage === 'checkout' && bundle && <Checkout state={state} bundle={bundle} onDone={setState} />}
                {(state.stage === 'checkout' || state.stage === 'booked') && state.savings && <Savings savings={state.savings} />}
                {state.suggestions && (state.stage === 'inspire' || state.stage === 'clarify') && (
                    <Destinations suggestions={state.suggestions} busy={busy} onPick={(id, name) => send({ action: { type: 'select_destination', id } }, `Собрать: ${name}`)} />
                )}
                {state.comparison && state.stage === 'compare' && (
                    <Comparison comparison={state.comparison} busy={busy} onTake={(id, name) => send({ action: { type: 'choose_compared', id } }, `Беру: ${name}`)} />
                )}
                {plan && plan.bundles && (state.stage === 'plan' || state.stage === 'checkout') && <PlanView state={state} send={send} busy={busy} />}
            </section>
        </main>
    );
}
