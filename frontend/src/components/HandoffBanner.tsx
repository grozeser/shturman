import type { Handoff } from '../types';

type Send = (body: { action: Record<string, unknown> }, label?: string) => void;

// Пока диалог у менеджера: видно, что человек подключается или уже на связи, и можно вернуться к агенту
export default function HandoffBanner({ handoff, send, busy }: { handoff: Handoff; send: Send; busy: boolean }) {
    const active = handoff.status === 'active';
    return (
        <div className={`handoff-banner ${active ? 'active' : ''}`} role="status">
            <i className="dot" aria-hidden="true" />
            <span>{active ? `На связи: ${handoff.operator}, менеджер` : 'Менеджер подключается — он видит ваш запрос, план и мои шаги'}</span>
            <button className="ghost" disabled={busy} onClick={() => send({ action: { type: 'handoff_cancel' } }, 'Вернуться к агенту')}>
                Вернуться к агенту
            </button>
        </div>
    );
}
