import { day, duration, money, temp } from '../format';
import type { Comparison as ComparisonData } from '../types';
import Cover from './Cover';
import Icon from './Icon';
import './Comparison.css';

// «Турция или Египет?» — собранные поездки рядом: цена от двери до двери, погода, дорога, виза, плюсы и минусы
export default function Comparison({ comparison, busy, onTake }: { comparison: ComparisonData; busy: boolean; onTake: (id: string, name: string) => void }) {
    const names = comparison.items.map((item) => item.name).join(' или ');
    return (
        <section className="card comparison" aria-labelledby="comparison-title">
            <header>
                <h2 id="comparison-title">{names}</h2>
                <span className="muted">собранные поездки рядом · цена от двери до двери</span>
            </header>
            <p className="comparison-verdict">
                <Icon name="sparkle" size={16} /> {comparison.verdict}
            </p>
            <div className="dest-grid comparison-grid">
                {comparison.items.map((item) => {
                    const top = item.id === comparison.winner;
                    const w = item.weather;
                    return (
                        <article key={item.id} className={`dest ${top ? 'top' : ''}`}>
                            <div className="dest-cover">
                                <Cover dest={item.id} seed={item.id} kinds={item.kinds} air={w?.air} water={w?.water} rain={w?.rain} height={150} title={item.name} />
                                {top && <span className="ribbon">мой выбор</span>}
                                <div className="dest-cover-text">
                                    <span>{item.country}</span>
                                    <h3>{item.name}</h3>
                                </div>
                            </div>
                            {item.error ? (
                                <p className="error">{item.error}</p>
                            ) : (
                                <>
                                    <div className="comparison-total">
                                        <b>{money(item.total!)}</b>
                                        <span className="muted">
                                            {money(item.per_person!)} на человека · {day(item.checkin!)} – {day(item.checkout!)}
                                        </span>
                                    </div>
                                    <div className="facts">
                                        {w?.air !== null && w?.air !== undefined && (
                                            <span>
                                                <Icon name="sun" size={16} /> днём {temp(w.air)}
                                            </span>
                                        )}
                                        {w?.water !== null && w?.water !== undefined && item.kinds.includes('sea') && (
                                            <span>
                                                <Icon name="wave" size={16} /> вода {temp(w.water)}
                                            </span>
                                        )}
                                        {w?.rain !== null && w?.rain !== undefined && (
                                            <span>
                                                <Icon name="umbrella" size={16} /> {w.rain} дн. с ливнями
                                            </span>
                                        )}
                                        <span>
                                            <Icon name={item.travel!.mode === 'train' ? 'train' : 'plane'} size={16} /> {duration(item.travel!.minutes)}
                                            {item.travel!.stops ? ` · через ${item.travel!.via}` : ' · прямой'}
                                        </span>
                                    </div>
                                    <dl className="comparison-rows">
                                        <dt>
                                            <Icon name="passport" size={16} />
                                        </dt>
                                        <dd>виза: {item.visa}</dd>
                                        <dt>
                                            <Icon name="bed" size={16} />
                                        </dt>
                                        <dd>
                                            {item.hotel!.name} {'★'.repeat(item.hotel!.stars)}, {item.hotel!.meal_label} · подходит вам на {item.hotel!.fit}/100
                                        </dd>
                                    </dl>
                                    {item.pros.length > 0 && (
                                        <ul className="why">
                                            {item.pros.map((pro) => (
                                                <li key={pro}>{pro}</li>
                                            ))}
                                        </ul>
                                    )}
                                    {item.cons.length > 0 && (
                                        <ul className="cons">
                                            {item.cons.map((con) => (
                                                <li key={con}>{con}</li>
                                            ))}
                                        </ul>
                                    )}
                                    <button className={top ? 'primary' : ''} disabled={busy} onClick={() => onTake(item.id, item.name)}>
                                        Беру эту — {item.name}
                                    </button>
                                </>
                            )}
                        </article>
                    );
                })}
            </div>
        </section>
    );
}
