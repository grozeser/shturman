import { useEffect, useState } from 'react';
import { NavLink, Route, Routes } from 'react-router-dom';
import { api } from './api';
import Icon, { type IconName } from './components/Icon';
import AgentPage from './pages/AgentPage';
import AuthPage from './pages/AuthPage';
import HotelsPage from './pages/HotelsPage';
import MetricsPage from './pages/MetricsPage';
import OperatorPage from './pages/OperatorPage';
import ProfilePage from './pages/ProfilePage';
import SharePage from './pages/SharePage';
import TripPage from './pages/TripPage';
import TripsPage from './pages/TripsPage';
import { initials, useAccount } from './useAccount';

// Четвёртое поле — короткая подпись для нижней панели на телефоне
const NAV: [string, string, IconName, string?][] = [
    ['/', 'Поездка', 'search', 'Поиск'],
    ['/trips', 'Мои поездки', 'suitcase', 'Поездки'],
    ['/profile', 'Память', 'person'],
    ['/hotels', 'Для отеля', 'hotel'],
    ['/metrics', 'Метрики', 'chart'],
];

function Logo() {
    return (
        <svg width="34" height="34" viewBox="0 0 64 64" aria-hidden="true">
            <rect width="64" height="64" rx="18" fill="#0b6b70" />
            <circle cx="32" cy="32" r="17" fill="none" stroke="#fff" strokeWidth="4" />
            <path d="M32 13l6 19-6 19-6-19z" fill="#ffcf70" />
            <circle cx="32" cy="32" r="3.5" fill="#fff" />
        </svg>
    );
}

export default function App() {
    const [mode, setMode] = useState<{ enabled: boolean; model: string | null } | null>(null);
    const account = useAccount();
    useEffect(() => {
        api.status()
            .then((s) => setMode(s.llm))
            .catch(() => setMode(null));
    }, []);
    return (
        <div className="app">
            <header className="topbar">
                <NavLink to="/" className="brand">
                    <Logo />
                    <span>
                        Штурман<small>поездка из одного запроса</small>
                    </span>
                </NavLink>
                <nav className="tabbar" aria-label="Разделы">
                    {NAV.map(([to, label, icon, short]) => (
                        <NavLink key={to} to={to} end={to === '/'}>
                            <Icon name={icon} />
                            <span className={short ? 'nav-full' : undefined}>{label}</span>
                            {short && <span className="nav-short">{short}</span>}
                        </NavLink>
                    ))}
                </nav>
                <div className="badges">
                    <span className="badge demo" title="Отели, рейсы и цены сгенерированы. Реальные: география, климат (Open-Meteo), закрытые аэропорты.">
                        демо-данные
                    </span>
                    {mode && (
                        <span className={`badge ${mode.enabled ? 'llm' : 'rules'}`} title={mode.enabled ? 'Запросы понимает LLM, цифры считают инструменты' : 'LLM не настроена — работает разбор на правилах'}>
                            {mode.enabled ? `LLM: ${mode.model}` : 'без LLM'}
                        </span>
                    )}
                </div>
                {/* Вход в шапке: «Войти» с иконкой человека; вошли — аватар с именем, ведёт в «Память» */}
                <div className="auth">
                    {account ? (
                        <NavLink to="/profile" className="account-chip" title={`${account.name} · ${account.email}`}>
                            <span className="avatar">{initials(account.name)}</span>
                            <span className="account-name">{account.name.split(' ')[0]}</span>
                        </NavLink>
                    ) : account === null ? (
                        <>
                            <NavLink to="/login" className="auth-login" aria-label="Войти">
                                <Icon name="person" />
                                <span>Войти</span>
                            </NavLink>
                            <NavLink to="/register" className="auth-register">
                                Регистрация
                            </NavLink>
                        </>
                    ) : null}
                </div>
            </header>
            <Routes>
                <Route path="/" element={<AgentPage />} />
                <Route path="/trips" element={<TripsPage />} />
                <Route path="/trips/:id" element={<TripPage />} />
                <Route path="/profile" element={<ProfilePage />} />
                <Route path="/hotels" element={<HotelsPage />} />
                <Route path="/metrics" element={<MetricsPage />} />
                <Route path="/login" element={<AuthPage mode="login" />} />
                <Route path="/register" element={<AuthPage mode="register" />} />
                <Route path="/share/:token" element={<SharePage />} />
                <Route path="/operator" element={<OperatorPage />} />
            </Routes>
        </div>
    );
}
