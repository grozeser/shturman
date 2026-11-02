import type { Bundle } from '../types';
import Icon, { type IconName } from './Icon';
import './Caught.css';

const KIND_ICON: Record<string, IconName> = { fixed: 'wrench', trap: 'warn', filtered: 'check' };

// «Что агент поймал за вас»: то, что при обычном поиске всплыло бы уже в дороге
export default function Caught({ bundle }: { bundle: Bundle }) {
    const items = bundle.caught ?? [];
    if (!items.length) return null;
    return (
        <section className="card caught" aria-labelledby="caught-title">
            <header>
                <h2 id="caught-title">Что я поймал за вас</h2>
                <span className="muted">при обычном поиске это всплыло бы уже в дороге</span>
            </header>
            <ul>
                {items.map((item) => (
                    <li key={item.title} className={`caught-${item.kind}`}>
                        <span className="caught-icon" aria-hidden="true">
                            <Icon name={KIND_ICON[item.kind] ?? 'check'} size={18} />
                        </span>
                        <div>
                            <b>{item.title}</b>
                            <span>{item.detail}</span>
                        </div>
                    </li>
                ))}
            </ul>
        </section>
    );
}
