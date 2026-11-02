import type { Booking, ConversationState, PassportCheck, StreamEvent } from './types';

const USER_KEY = 'shturman.user';

function userId(): string {
    const key = USER_KEY;
    try {
        const existing = localStorage.getItem(key);
        if (existing) return existing;
        const created = `u-${crypto.randomUUID().slice(0, 18)}`;
        localStorage.setItem(key, created);
        return created;
    } catch {
        return 'u-anonymous-session';
    }
}

const USER = userId();

/**
 * Вход — это смена user_id браузера: поездки, память и диалоги привязаны к нему. Текущий диалог забываем
 * и перезагружаем приложение, чтобы все запросы ушли уже от имени аккаунта.
 */
export function switchUser(id: string, to = '/trips') {
    try {
        localStorage.setItem(USER_KEY, id);
        localStorage.removeItem('shturman.conversation');
    } catch {
        /* приватный режим: вход проживёт до перезагрузки */
    }
    window.location.assign(to);
}

export function logout() {
    switchUser(`u-${crypto.randomUUID().slice(0, 18)}`, '/');
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(path, {
        ...init,
        headers: { 'Content-Type': 'application/json', 'X-User-Id': USER, ...(init.headers ?? {}) },
    });
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === 'string' ? body.detail : `Ошибка ${response.status}`);
    }
    return response.json() as Promise<T>;
}

export const api = {
    status: () => request<{ llm: { enabled: boolean; model: string | null; mode: string }; today: string }>('/api/status'),
    createConversation: () => request<ConversationState>('/api/conversations', { method: 'POST' }),
    conversation: (id: string) => request<ConversationState>(`/api/conversations/${id}`),
    dates: (id: string) => request<DateOption[]>(`/api/conversations/${id}/dates`),
    share: (id: string) => request<{ token: string }>(`/api/conversations/${id}/share`, { method: 'POST' }),
    myShare: (id: string) => request<GroupShare | null>(`/api/conversations/${id}/share`),
    shared: (token: string) => request<GroupShare>(`/api/shared/${encodeURIComponent(token)}`),
    vote: (token: string, name: string, choice: number) =>
        request<GroupShare>(`/api/shared/${encodeURIComponent(token)}/vote`, { method: 'POST', body: JSON.stringify({ name, choice }) }),
    checkout: (id: string, name: string, email: string, insurance?: boolean) =>
        request<{ booking: Booking; state: ConversationState }>(`/api/conversations/${id}/checkout`, {
            method: 'POST',
            body: JSON.stringify({ name, email, insurance }),
        }),
    passport: (id: string, until: string) =>
        request<PassportCheck>(`/api/conversations/${id}/passport`, { method: 'POST', body: JSON.stringify({ until }) }),
    bookings: () => request<Booking[]>('/api/bookings'),
    booking: (id: string) => request<Booking>(`/api/bookings/${id}`),
    /** Файл .ics: обычная ссылка не передала бы X-User-Id, поэтому качаем fetch и отдаём как Blob. */
    calendarFile: async (id: string) => {
        const response = await fetch(`/api/bookings/${id}/calendar.ics`, { headers: { 'X-User-Id': USER } });
        if (!response.ok) throw new Error(`Ошибка ${response.status}`);
        const link = document.createElement('a');
        link.href = URL.createObjectURL(await response.blob());
        link.download = `trip-${id.replace(/[^A-Z0-9]/gi, '')}.ics`;
        link.click();
        URL.revokeObjectURL(link.href);
    },
    bookingAction: (id: string, post: Record<string, unknown>) =>
        request<{ booking: Booking; text: string; quick: unknown[] }>(`/api/bookings/${id}/actions`, {
            method: 'POST',
            body: JSON.stringify({ post }),
        }),
    profile: () => request<Profile>('/api/profile'),
    forget: (key: string) => request<Profile>(`/api/profile/facts/${key}`, { method: 'DELETE' }),
    forgetAll: () => request<Profile>('/api/profile', { method: 'DELETE' }),
    metrics: () => request<Metrics>('/api/metrics'),
    destinations: () => request<{ id: string; name: string; country: string }[]>('/api/destinations'),
    hotels: (dest: string) => request<HotelRow[]>(`/api/hotels?dest=${encodeURIComponent(dest)}`),
    hotel: (id: string) => request<HotelReport>(`/api/hotels/${encodeURIComponent(id)}`),
    operatorQueue: (key: string) => request<QueueRow[]>('/api/operator/queue', { headers: { 'X-Operator-Key': key } }),
    operatorConversation: (key: string, id: string) => request<ConversationState>(`/api/operator/conversations/${id}`, { headers: { 'X-Operator-Key': key } }),
    operatorReply: (key: string, id: string, text: string, operator: string) =>
        request<ConversationState>(`/api/operator/conversations/${id}/reply`, { method: 'POST', headers: { 'X-Operator-Key': key }, body: JSON.stringify({ text, operator }) }),
    operatorClose: (key: string, id: string, operator: string) =>
        request<ConversationState>(`/api/operator/conversations/${id}/close`, { method: 'POST', headers: { 'X-Operator-Key': key }, body: JSON.stringify({ operator }) }),
    me: () => request<Account | null>('/api/accounts/me'),
    demoAccounts: () => request<DemoAccount[]>('/api/accounts/demo'),
    login: (email: string, password: string) => request<Account>('/api/accounts/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
    register: (name: string, email: string, password: string) =>
        request<Account>('/api/accounts/register', { method: 'POST', body: JSON.stringify({ name, email, password }) }),
};

/** Строка очереди в консоли оператора: кто ждёт менеджера, почему и что уже собрано. */
export interface QueueRow {
    id: string;
    channel: 'web' | 'telegram';
    status: 'waiting' | 'active';
    reason: string;
    since: number;
    updated: number;
    unread: number;
    operator: string | null;
    last_message: string;
    trip: string | null;
    stage: string;
}

export interface Account {
    user_id: string;
    name: string;
    email: string;
    demo: boolean;
}

export interface DemoAccount {
    user_id: string;
    name: string;
    email: string;
    password: string;
    about: string;
    trips: string[];
}

export interface HotelRow {
    id: string;
    name: string;
    stars: number;
    rating: number;
    segments: Record<string, number>;
    recommended: number;
    rejected: number;
    booked: number;
}

export interface HotelReport {
    hotel: { id: string; name: string; stars: number; rating: number; area: string; beach_m: number | null; center_km: number; features: Record<string, boolean>; meals: string[]; dest_name: string };
    segments: Record<string, { label: string; score: number; excluded: string | null; pros: string[]; cons: string[] }>;
    best_for: string[];
    improvements: { feature: string; title: string; gains: Record<string, number>; opens: string[]; total: number }[];
    stats: { recommended: number; rejected: number; booked: number; segments: Record<string, number>; reasons: Record<string, number> };
}

export interface Profile {
    facts?: Record<string, { value: unknown; label: string }>;
    trips?: { dest: string; checkin: string; nights: number; total: number }[];
    notes?: string[];
}

export interface Metrics {
    live: Record<string, number | null>;
    business: {
        funnel: { step: string; count: number }[];
        bookings: number;
        avg_check: number | null;
        gmv: number;
        avg_minutes_saved?: number | null;
        avg_clicks_saved?: number | null;
        avg_messages?: number | null;
        package_share: number | null;
        upsell_share: number | null;
        insurance_share?: number | null;
        post_purchase_actions: number;
    };
    eval: null | {
        generated: string;
        mode: string;
        summary: Record<string, number | string>;
        cases: { id: string; text: string; ok: boolean; turns: number; clarifications: number; problems: string[] }[];
    };
}

/** Поездка компанией: снимок вариантов по ссылке и голоса попутчиков. */
export interface GroupShare {
    token: string;
    title: string;
    dates: string;
    nights: number;
    party: string;
    people: number;
    options: { id: string; label: string; total: number; per_person: number; hotel: string; road: string; why: string[] }[];
    counts: number[];
    voters: { name: string; choice: number }[];
    leader: number | null;
    mine: { name: string; choice: number }[];
}

/** День в календаре «а если сдвинуть заезд»: цена той же поездки и разница с текущим планом. */
export interface DateOption {
    date: string;
    offset: number;
    available: boolean;
    total: number | null;
    delta: number | null;
    same_hotel: boolean | null;
    cheapest: boolean;
}

/** Ход агента потоком (SSE поверх fetch): шаги приходят по мере работы, в конце — ответ и новое состояние. */
export async function streamTurn(
    conversationId: string,
    body: { text?: string; action?: Record<string, unknown> },
    onEvent: (event: StreamEvent) => void,
): Promise<void> {
    const response = await fetch(`/api/conversations/${conversationId}/turn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Id': USER, Accept: 'text/event-stream' },
        body: JSON.stringify(body),
    });
    if (!response.ok || !response.body) throw new Error(`Агент недоступен (${response.status})`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let index: number;
        while ((index = buffer.indexOf('\n\n')) >= 0) {
            const chunk = buffer.slice(0, index);
            buffer = buffer.slice(index + 2);
            const data = chunk
                .split('\n')
                .filter((line) => line.startsWith('data: '))
                .map((line) => line.slice(6))
                .join('\n');
            if (data) onEvent(JSON.parse(data) as StreamEvent);
        }
    }
}
