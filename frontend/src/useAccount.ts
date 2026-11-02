import { useEffect, useState } from 'react';
import { api, type Account } from './api';

let request: Promise<Account | null> | null = null;

/** Аккаунт этого браузера: undefined — ещё грузится, null — не вошли. Один запрос на всё приложение. */
export function useAccount(): Account | null | undefined {
    const [account, setAccount] = useState<Account | null | undefined>(undefined);
    useEffect(() => {
        request ??= api.me().catch(() => null);
        let alive = true;
        request.then((value) => alive && setAccount(value));
        return () => {
            alive = false;
        };
    }, []);
    return account;
}

export function initials(name: string): string {
    return name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((word) => word[0].toUpperCase())
        .join('');
}
