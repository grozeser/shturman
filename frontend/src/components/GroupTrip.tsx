import { useEffect, useState } from 'react';
import { api, type GroupShare } from '../api';
import { money, plural } from '../format';
import type { ConversationState } from '../types';
import './GroupTrip.css';

type Send = (body: { action: Record<string, unknown> }, label?: string) => void;

export function VoteBars({ share }: { share: GroupShare }) {
    const total = share.counts.reduce((a, b) => a + b, 0);
    return (
        <ul className="vote-bars">
            {share.options.map((option, index) => {
                const names = share.voters.filter((v) => v.choice === index).map((v) => v.name);
                return (
                    <li key={option.id} className={share.leader === index ? 'leader' : ''}>
                        <div className="vote-row">
                            <b>«{option.label}»</b>
                            <span>
                                {money(option.total)} · {money(option.per_person)} с человека
                            </span>
                        </div>
                        <div className="vote-track" aria-hidden="true">
                            <i style={{ width: total ? `${(100 * share.counts[index]) / total}%` : 0 }} />
                        </div>
                        <small className="muted">
                            {share.counts[index]} {plural(share.counts[index], 'голос', 'голоса', 'голосов')}
                            {names.length ? `: ${names.join(', ')}` : ''}
                        </small>
                    </li>
                );
            })}
        </ul>
    );
}

// Карточка организатора: позвать попутчиков, следить за голосами и выбрать вариант большинства
export default function GroupTrip({ state, send, busy }: { state: ConversationState; send: Send; busy: boolean }) {
    const [share, setShare] = useState<GroupShare | null>(null);
    const [copied, setCopied] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const plan = state.plan!;

    useEffect(() => {
        let alive = true;
        const load = () =>
            api.myShare(state.id)
                .then((s) => alive && setShare(s))
                .catch(() => undefined);
        load();
        const timer = window.setInterval(load, 5000); // голоса приходят из других браузеров — подтягиваем раз в 5 секунд
        return () => {
            alive = false;
            window.clearInterval(timer);
        };
    }, [state.id]);

    const invite = async () => {
        setError(null);
        try {
            const { token } = await api.share(state.id);
            setShare(await api.shared(token));
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Не получилось');
        }
    };
    const link = share ? `${window.location.origin}/share/${share.token}` : '';
    const copy = async () => {
        try {
            await navigator.clipboard.writeText(link);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2000);
        } catch {
            setError('Не удалось скопировать — выделите ссылку вручную');
        }
    };
    const stale = share && share.options.some((o) => !plan.bundles.some((b) => b.id === o.id));
    const winner = share && share.leader !== null ? plan.bundles.findIndex((b) => b.id === share.options[share.leader!].id) : -1;

    return (
        <section className="card group-trip">
            <header>
                <h2>Едете компанией?</h2>
                <span className="muted">попутчики голосуют за вариант и видят свою долю — без регистрации</span>
            </header>
            {!share ? (
                <button disabled={busy} onClick={invite}>
                    Позвать попутчиков
                </button>
            ) : (
                <>
                    <div className="share-link">
                        <input readOnly value={link} aria-label="Ссылка для попутчиков" onFocus={(e) => e.currentTarget.select()} />
                        <button onClick={copy}>{copied ? 'Скопировано' : 'Скопировать'}</button>
                        <a className="button ghost" href={link} target="_blank" rel="noreferrer">
                            Открыть
                        </a>
                    </div>
                    <VoteBars share={share} />
                    {stale ? (
                        <p className="muted small">
                            После приглашения вы пересобрали план — у попутчиков старые варианты.{' '}
                            <button className="link" disabled={busy} onClick={invite}>
                                Позвать заново
                            </button>
                        </p>
                    ) : (
                        winner >= 0 &&
                        winner !== state.selected && (
                            <button className="primary" disabled={busy} onClick={() => send({ action: { type: 'select_bundle', index: winner } }, `Вариант «${plan.bundles[winner].label}» — за него большинство`)}>
                                Выбрать «{plan.bundles[winner].label}» — за него большинство
                            </button>
                        )
                    )}
                </>
            )}
            {error && <p className="error">{error}</p>}
        </section>
    );
}
