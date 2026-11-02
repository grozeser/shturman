import type { Chip } from '../types';

const KIND_LABEL: Record<Chip['kind'], string> = {
    explicit: 'вы сказали',
    inferred: 'я вывел',
    memory: 'из памяти',
    default: 'допущение',
};

export default function Brief({ chips, onRemove, busy }: { chips: Chip[]; onRemove: (chip: Chip) => void; busy: boolean }) {
    const removable = (chip: Chip) => !['origin', 'destination', 'dates', 'party'].includes(chip.key) && chip.kind !== 'default';
    return (
        <section className="card brief">
            <header>
                <h2>Я понял так</h2>
                <div className="legend">
                    {(['explicit', 'inferred', 'memory', 'default'] as const).map((kind) => (
                        <span key={kind} className={`dot ${kind}`}>
                            {KIND_LABEL[kind]}
                        </span>
                    ))}
                </div>
            </header>
            <div className="chips">
                {chips.map((chip) => (
                    <span key={chip.key} className={`chip ${chip.kind}`} title={chip.reason ? `${KIND_LABEL[chip.kind]}: ${chip.reason}` : KIND_LABEL[chip.kind]}>
                        <span className="chip-label">{chip.label}</span>
                        {chip.reason && chip.kind !== 'explicit' && <em>{chip.reason}</em>}
                        {removable(chip) && (
                            <button disabled={busy} onClick={() => onRemove(chip)} aria-label={`Убрать: ${chip.label}`}>
                                ×
                            </button>
                        )}
                    </span>
                ))}
            </div>
            <p className="hint">Что-то не так — уберите условие крестиком или просто напишите в чат, план пересоберётся.</p>
        </section>
    );
}
