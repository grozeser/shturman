import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, type GroupShare } from '../api';
import { VoteBars } from '../components/GroupTrip';
import '../components/GroupTrip.css';
import { money } from '../format';

const NAME_KEY = 'shturman.voter-name';

function savedName(): string {
    try {
        return localStorage.getItem(NAME_KEY) ?? '';
    } catch {
        return '';
    }
}

// Страница попутчика по ссылке: варианты поездки, своя доля и голос — без входа и без чата организатора
export default function SharePage() {
    const { token } = useParams();
    const [share, setShare] = useState<GroupShare | null>(null);
    const [name, setName] = useState(savedName);
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!token) return;
        let alive = true;
        const load = () =>
            api.shared(token)
                .then((s) => alive && setShare(s))
                .catch((e: Error) => alive && setError(e.message));
        load();
        const timer = window.setInterval(load, 5000);
        return () => {
            alive = false;
            window.clearInterval(timer);
        };
    }, [token]);

    if (error && !share) return <main className="page error">{error}</main>;
    if (!share) return <main className="page loading">Загружаю поездку…</main>;
    const mine = share.mine.find((v) => v.name === name.trim());
    const vote = async (choice: number) => {
        const clean = name.trim();
        if (!clean) {
            setError('Напишите своё имя — так остальные поймут, чей голос');
            return;
        }
        setBusy(true);
        setError(null);
        try {
            setShare(await api.vote(share.token, clean, choice));
            try {
                localStorage.setItem(NAME_KEY, clean);
            } catch {
                /* приватный режим: имя придётся ввести ещё раз */
            }
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Не получилось');
        } finally {
            setBusy(false);
        }
    };

    return (
        <main className="page share-page">
            <h1>Едем вместе: {share.title}</h1>
            <p className="muted">
                {share.dates} · {share.nights} ноч. · {share.party}. Выберите вариант, который нравится вам, — организатор увидит голоса и оформит тот, за
                который большинство. Цены — за всех и с одного человека.
            </p>
            <label className="who">
                Ваше имя
                <input value={name} maxLength={40} onChange={(e) => setName(e.target.value)} placeholder="например, Оля" />
                {mine && <span className="muted small">вы голосуете за «{share.options[mine.choice].label}»</span>}
            </label>
            <div className="options">
                {share.options.map((option, index) => (
                    <article key={option.id} className={`card option${mine?.choice === index ? ' picked' : ''}`}>
                        <h2>«{option.label}»</h2>
                        <span className="per-person">{money(option.per_person)}</span>
                        <span className="muted small">с человека · {money(option.total)} за всех</span>
                        <span>{option.hotel}</span>
                        {!option.why.includes(option.road) && <span className="muted small">{option.road}</span>}
                        {option.why.length > 0 && (
                            <ul>
                                {option.why.map((reason) => (
                                    <li key={reason}>{reason}</li>
                                ))}
                            </ul>
                        )}
                        <button className={mine?.choice === index ? 'primary' : ''} disabled={busy} onClick={() => vote(index)}>
                            {mine?.choice === index ? 'Ваш голос' : 'Голосую за этот'}
                        </button>
                    </article>
                ))}
            </div>
            {error && <p className="error">{error}</p>}
            <section className="card">
                <h2>Как голосуют</h2>
                <VoteBars share={share} />
            </section>
            <p className="muted small">
                Это демо: отели, рейсы и цены сгенерированы. <Link to="/">Собрать свою поездку</Link>
            </p>
        </main>
    );
}
