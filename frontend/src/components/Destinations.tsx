import { duration, money, temp } from '../format';
import type { ConversationState } from '../types';
import Cover from './Cover';
import Icon from './Icon';

const MONTHS = ['январе', 'феврале', 'марте', 'апреле', 'мае', 'июне', 'июле', 'августе', 'сентябре', 'октябре', 'ноябре', 'декабре'];

export default function Destinations({ suggestions, onPick, busy }: { suggestions: NonNullable<ConversationState['suggestions']>; onPick: (id: string, name: string) => void; busy: boolean }) {
    return (
        <section className="card">
            <header>
                <h2>Куда поехать в {MONTHS[suggestions.month - 1]}</h2>
                <span className="muted">проверено {suggestions.checked} направлений</span>
            </header>
            <div className="dest-grid">
                {suggestions.items.map((item, index) => (
                    <article key={item.id} className={`dest ${index === 0 ? 'top' : ''}`}>
                        <div className="dest-cover">
                            <Cover dest={item.id} seed={item.id} kinds={item.kinds} air={item.weather.air} water={item.weather.water} rain={item.weather.rain} height={176} title={item.name} />
                            {index === 0 && <span className="ribbon">лучше всего подходит</span>}
                            <div className="dest-cover-text">
                                <span>{item.country}</span>
                                <h3>{item.name}</h3>
                                <div className="price">
                                    от <b>{money(item.price_from)}</b>
                                    <small>за всё на вашу компанию</small>
                                </div>
                            </div>
                        </div>
                        <div className="facts">
                            {item.weather.water !== null && item.kinds.includes('sea') ? (
                                <span title="Средняя температура моря за 2022–2024">
                                    <Icon name="wave" size={16} /> {temp(item.weather.water)}
                                </span>
                            ) : null}
                            <span title="Средний дневной максимум за 10 лет">
                                <Icon name="sun" size={16} /> {temp(item.weather.air)}
                            </span>
                            {item.weather.rain !== null && (
                                <span title="Дней с ливнями ≥ 5 мм">
                                    <Icon name="umbrella" size={16} /> {item.weather.rain} дн.
                                </span>
                            )}
                            <span>
                                <Icon name={item.travel.mode === 'train' ? 'train' : 'plane'} size={16} /> {duration(item.travel.minutes)}
                                {item.travel.stops ? ' · пересадка' : ''}
                            </span>
                        </div>
                        <ul className="why">
                            {item.why.map((reason) => (
                                <li key={reason}>{reason}</li>
                            ))}
                        </ul>
                        {item.cons.length > 0 && (
                            <ul className="cons">
                                {item.cons.map((con) => (
                                    <li key={con}>{con}</li>
                                ))}
                            </ul>
                        )}
                        <p className="highlights">{item.highlights.join(' · ')}</p>
                        <button className="primary" disabled={busy} onClick={() => onPick(item.id, item.name)}>
                            Собрать поездку
                        </button>
                    </article>
                ))}
            </div>
            {suggestions.rejected.length > 0 && (
                <div className="rejected">
                    <b>Почему не туда:</b>
                    {suggestions.rejected.map((r) => (
                        <span key={r.id}>
                            {r.name} — {r.reason}
                        </span>
                    ))}
                </div>
            )}
        </section>
    );
}
