import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, logout, type Profile } from '../api';
import { day, money } from '../format';
import { initials, useAccount } from '../useAccount';

export default function ProfilePage() {
    const [profile, setProfile] = useState<Profile | null>(null);
    const account = useAccount();
    useEffect(() => {
        api.profile()
            .then(setProfile)
            .catch(() => setProfile({}));
    }, []);
    if (!profile) return <main className="page loading">Загружаю…</main>;
    const facts = Object.entries(profile.facts ?? {});
    return (
        <main className="page">
            {account !== undefined && (
                <section className="card account-card">
                    {account ? (
                        <>
                            <span className="avatar big">{initials(account.name)}</span>
                            <div>
                                <b>{account.name}</b>
                                <span className="muted">
                                    {account.email}
                                    {account.demo ? ' · тестовый пользователь' : ''}
                                </span>
                            </div>
                            <button className="ghost" onClick={logout}>
                                Выйти
                            </button>
                        </>
                    ) : (
                        <>
                            <div>
                                <b>Вы не вошли в аккаунт</b>
                                <span className="muted">Войдите или зарегистрируйтесь — поездки и память будут сохраняться в аккаунте.</span>
                            </div>
                            <Link className="button primary" to="/login">
                                Войти
                            </Link>
                            <Link className="button" to="/register">
                                Регистрация
                            </Link>
                        </>
                    )}
                </section>
            )}
            <h1>Что я о вас помню</h1>
            <p className="muted">Это подставляется в следующие поездки и помечается в брифе как «из памяти». Любой пункт можно забыть.</p>
            <section className="card">
                {facts.length ? (
                    <ul className="facts-list">
                        {facts.map(([key, fact]) => (
                            <li key={key}>
                                <span>{fact.label}</span>
                                <button className="ghost" onClick={() => api.forget(key).then(setProfile)}>
                                    Забыть
                                </button>
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p className="muted">Пока ничего: память появляется после первой оформленной поездки.</p>
                )}
                {profile.notes && profile.notes.length > 0 && (
                    <>
                        <h3 className="sub">Просили запомнить</h3>
                        <ul>
                            {profile.notes.map((note) => (
                                <li key={note}>{note}</li>
                            ))}
                        </ul>
                    </>
                )}
                {(facts.length > 0 || profile.trips?.length) && (
                    <button className="danger" onClick={() => api.forgetAll().then(setProfile)}>
                        Забыть всё
                    </button>
                )}
            </section>
            {profile.trips && profile.trips.length > 0 && (
                <section className="card">
                    <h2>Прошлые поездки</h2>
                    <ul className="facts-list">
                        {profile.trips.map((t) => (
                            <li key={t.dest + t.checkin}>
                                <span>
                                    {t.dest}, с {day(t.checkin)}, {t.nights} ноч.
                                </span>
                                <b>{money(t.total)}</b>
                            </li>
                        ))}
                    </ul>
                </section>
            )}
        </main>
    );
}
