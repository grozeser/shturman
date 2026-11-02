import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, switchUser, type Account, type DemoAccount } from '../api';
import Cover from '../components/Cover';
import Icon from '../components/Icon';
import { plural } from '../format';
import { initials } from '../useAccount';

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Вход и регистрация: фото на фоне, карточка с действиями по центру. */
export default function AuthPage({ mode }: { mode: 'login' | 'register' }) {
    const [demo, setDemo] = useState<DemoAccount[] | null>(null);
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [busy, setBusy] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        setError(null);
        if (mode === 'login')
            api.demoAccounts()
                .then(setDemo)
                .catch(() => setDemo([]));
    }, [mode]);

    const enter = async (key: string, run: () => Promise<Account>) => {
        setBusy(key);
        setError(null);
        try {
            switchUser((await run()).user_id);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Не получилось');
            setBusy(null);
        }
    };
    const valid = EMAIL.test(email.trim()) && (mode === 'login' ? password.length > 0 : name.trim().length >= 2 && password.length >= 6);
    const submit = () => {
        if (!valid || busy) return;
        void enter('form', () => (mode === 'login' ? api.login(email.trim(), password) : api.register(name.trim(), email.trim(), password)));
    };

    return (
        <main className="auth-page">
            <Cover dest="seychelles" seed="auth" kinds={['sea']} title="Сейшелы" />
            <section className="auth-card">
                <h1>{mode === 'login' ? 'Войдите, чтобы увидеть свои поездки' : 'Регистрация'}</h1>
                {mode === 'login' ? (
                    <>
                        <p className="muted">Тестовые пользователи уже с покупками — вход в один клик.</p>
                        <ul className="demo-users">
                            {demo?.map((user) => (
                                <li key={user.user_id}>
                                    <button disabled={Boolean(busy)} onClick={() => void enter(user.user_id, () => api.login(user.email, user.password))}>
                                        <span className="avatar">{initials(user.name)}</span>
                                        <span className="demo-user-text">
                                            <b>{user.name}</b>
                                            <small>{user.about}</small>
                                            <small className="demo-trips">
                                                {user.trips.length} {plural(user.trips.length, 'поездка', 'поездки', 'поездок')}: {user.trips.join(', ')}
                                            </small>
                                        </span>
                                        <Icon name="chevron" />
                                    </button>
                                    <small className="demo-cred">
                                        {user.email} · пароль {user.password}
                                    </small>
                                </li>
                            ))}
                            {demo === null && <li className="muted">Загружаю тестовых пользователей…</li>}
                        </ul>
                        <div className="auth-divider">
                            <span>или по почте</span>
                        </div>
                    </>
                ) : (
                    <p className="muted">Поездки и память агента из этого браузера сохранятся в аккаунте.</p>
                )}
                <form
                    className="auth-form"
                    onSubmit={(event) => {
                        event.preventDefault();
                        submit();
                    }}
                >
                    {mode === 'register' && (
                        <label>
                            Имя
                            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" placeholder="Анна Иванова" />
                        </label>
                    )}
                    <label>
                        Почта
                        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="email" placeholder="anna@example.com" />
                    </label>
                    <label>
                        Пароль
                        <input
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            type="password"
                            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                            placeholder={mode === 'register' ? 'не короче 6 символов' : ''}
                        />
                    </label>
                    <button className="primary big" disabled={!valid || Boolean(busy)}>
                        {busy === 'form' ? 'Секунду…' : mode === 'login' ? 'Войти' : 'Зарегистрироваться'}
                    </button>
                    {error && <p className="error">{error}</p>}
                </form>
                <p className="auth-switch">
                    {mode === 'login' ? (
                        <>
                            Нет аккаунта? <Link to="/register">Зарегистрироваться</Link>
                        </>
                    ) : (
                        <>
                            Уже есть аккаунт? <Link to="/login">Войти</Link>
                        </>
                    )}
                </p>
            </section>
        </main>
    );
}
