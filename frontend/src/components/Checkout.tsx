import { useEffect, useState } from 'react';
import { api } from '../api';
import { day, money } from '../format';
import type { Bundle, ConversationState, PassportCheck } from '../types';
import './Checkout.css';

export default function Checkout({ state, bundle, onDone }: { state: ConversationState; bundle: Bundle; onDone: (s: ConversationState) => void }) {
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [paying, setPaying] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const docs = state.documents;
    const policy = docs?.insurance;
    // галочку могли поставить и словами в чате («со страховкой») — тогда состояние приходит с сервера
    const chosen = Boolean(state.checkout_options?.insurance);
    const [insured, setInsured] = useState(chosen);
    useEffect(() => setInsured(chosen), [chosen]);
    const [passport, setPassport] = useState(state.passport_until ?? '');
    const [check, setCheck] = useState<PassportCheck | null>(docs?.passport_check ?? null);
    useEffect(() => setCheck(docs?.passport_check ?? null), [docs?.passport_check]);
    const total = bundle.total + (insured && policy ? policy.price : 0);
    const verify = (value: string) => {
        setPassport(value);
        if (/^\d{4}-\d{2}-\d{2}$/.test(value))
            api.passport(state.id, value)
                .then(setCheck)
                .catch(() => setCheck(null));
    };
    const lines: [string, number][] = bundle.legs
        ? bundle.legs.flatMap((leg, index) => [
              ...(index === 0 ? [[`Дорога туда · ${leg.outbound.number}`, leg.outbound.cost ?? 0] as [string, number]] : []),
              [`${leg.dest_name}: ${leg.hotel.name}, ${leg.nights} ноч., ${leg.hotel.meal_label}`, leg.costs.hotel + leg.costs.meals] as [string, number],
              [`${leg.dest_name}: трансферы`, leg.costs.transfers] as [string, number],
              [index < bundle.legs!.length - 1 ? `Переезд ${leg.dest_name} → ${bundle.legs![index + 1].dest_name}` : `Дорога домой · ${leg.inbound.number}`, leg.inbound.cost ?? 0] as [string, number],
              ...leg.extras.map((e) => [e.title, e.price] as [string, number]),
          ])
        : [
        [`${bundle.outbound.mode === 'train' ? 'Поезд' : 'Перелёт'} туда · ${bundle.outbound.number}`, bundle.outbound.cost ?? 0],
        [`${bundle.inbound.mode === 'train' ? 'Поезд' : 'Перелёт'} обратно · ${bundle.inbound.number}`, bundle.inbound.cost ?? 0],
        [`${bundle.hotel.name}, ${bundle.nights} ноч.`, bundle.costs.hotel],
        [`Питание: ${bundle.hotel.meal_label}`, bundle.costs.meals],
        [`Трансферы: ${bundle.transfer_in.title.toLowerCase()}`, bundle.costs.transfers],
        ...bundle.extras.map((e) => [e.title, e.price] as [string, number]),
          ];
    const errors = bundle.checks.filter((c) => c.status === 'error');
    const pay = async () => {
        setPaying(true);
        setError(null);
        try {
            await new Promise((resolve) => setTimeout(resolve, 900)); // видимая «обработка платежа» в имитации
            const result = await api.checkout(state.id, name, email, policy ? insured : undefined);
            onDone(result.state);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Не удалось оформить');
        } finally {
            setPaying(false);
        }
    };
    const valid = name.trim().length >= 2 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
    return (
        <section className="card checkout">
            <header>
                <h2>Корзина</h2>
                <span className="muted">
                    {bundle.dest_name}, {day(bundle.checkin)} – {day(bundle.checkout)}
                </span>
            </header>
            <div className="checkout-body">
                <div className="checkout-summary">
                    <ul className="cart">
                        {lines.map(([title, price]) => (
                            <li key={title}>
                                <span>{title}</span>
                                <b>{price ? money(price) : 'в цене'}</b>
                            </li>
                        ))}
                        {insured && policy && (
                            <li>
                                <span>{policy.title}</span>
                                <b>{money(policy.price)}</b>
                            </li>
                        )}
                        <li className="sum">
                            <span>Итого</span>
                            <b>{money(total)}</b>
                        </li>
                    </ul>
                    {policy && (
                        <label className={`policy${insured ? ' on' : ''}`}>
                            <input type="checkbox" checked={insured} onChange={(e) => setInsured(e.target.checked)} />
                            <span>
                                <b>
                                    {policy.title} — {money(policy.price)}
                                </b>
                                <small>
                                    покрытие {policy.coverage}, на {policy.people} чел. и {policy.days} дн.: {policy.includes.join(', ')}
                                    {policy.required ? ' · для визы обязательна' : ''}
                                </small>
                            </span>
                        </label>
                    )}
                    {docs?.passport && (
                        <div className={`passport${check ? (check.ok ? ' ok' : ' bad') : ''}`}>
                            <label>
                                Загранпаспорт действует до
                                <input type="date" value={passport} onChange={(e) => verify(e.target.value)} />
                            </label>
                            <small>{check?.text ?? `${docs.passport.rule}: нужен паспорт, действующий до ${day(docs.passport.required)} ${docs.passport.required.slice(0, 4)} или дольше.`}</small>
                        </div>
                    )}
                    <p className="muted">
                        {bundle.hotel.refundable && bundle.hotel.free_cancel_until ? `Отель можно отменить бесплатно до ${day(bundle.hotel.free_cancel_until)}.` : 'Тариф отеля невозвратный.'} Проверок
                        стыковок пройдено: {bundle.checks.filter((c) => c.status === 'ok' || c.status === 'fixed').length} из {bundle.checks.length}.
                    </p>
                    {errors.length > 0 && <p className="error">Критично: {errors.map((e) => e.title).join('; ')}</p>}
                </div>
                <form
                    onSubmit={(e) => {
                        e.preventDefault();
                        if (valid && !paying) void pay();
                    }}
                >
                    <label>
                        Имя путешественника
                        <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" placeholder="Анна Иванова" />
                    </label>
                    <label>
                        Почта для ваучера
                        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="email" placeholder="anna@example.com" />
                    </label>
                    <button className="primary big" disabled={!valid || paying}>
                        {paying ? 'Оплачиваю…' : `Оплатить ${money(total)} (имитация)`}
                    </button>
                    <p className="muted small">Это демо: деньги не списываются, данные карты не запрашиваются.</p>
                    {error && <p className="error">{error}</p>}
                </form>
            </div>
        </section>
    );
}
