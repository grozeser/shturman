import type { Bundle } from '../types';
import Icon, { type IconName } from './Icon';
import './Hacks.css';

const KIND_ICON: Record<string, IconName> = { night_train: 'train', layover_city: 'plane', later_return: 'sun' };

type Send = (body: { action: Record<string, unknown> }, label?: string) => void;

// Лайфхаки: неочевидное, что агент нашёл в уже собранных расписаниях, — применяется одной кнопкой
export default function Hacks({ bundle, send, busy }: { bundle: Bundle; send: Send; busy: boolean }) {
    const hacks = bundle.hacks ?? [];
    if (!hacks.length) return null;
    return (
        <section className="card hacks" aria-labelledby="hacks-title">
            <header>
                <h2 id="hacks-title">Лайфхаки для этой поездки</h2>
                <span className="muted">нашёл в расписаниях — обычный поиск такого не покажет</span>
            </header>
            <ul>
                {hacks.map((hack) => (
                    <li key={hack.kind}>
                        <span className="hacks-icon" aria-hidden="true">
                            <Icon name={KIND_ICON[hack.kind] ?? 'sparkle'} size={18} />
                        </span>
                        <div>
                            <b>{hack.title}</b>
                            <span>{hack.detail}</span>
                        </div>
                        {hack.action && hack.label && (
                            <button disabled={busy} onClick={() => send({ action: hack.action! }, hack.label!)}>
                                {hack.label}
                            </button>
                        )}
                    </li>
                ))}
            </ul>
        </section>
    );
}
