import { useCallback, useEffect, useRef, useState } from 'react';
import { api, streamTurn } from './api';
import type { ConversationState, Step } from './types';

const KEY = 'shturman.conversation';

function savedId(): string | null {
    try {
        return localStorage.getItem(KEY);
    } catch {
        return null;
    }
}

function remember(id: string) {
    try {
        localStorage.setItem(KEY, id);
    } catch {
        /* приватный режим: диалог просто не переживёт перезагрузку */
    }
}

export function useAgent() {
    const [state, setState] = useState<ConversationState | null>(null);
    const [busy, setBusy] = useState(false);
    const [liveSteps, setLiveSteps] = useState<Step[]>([]);
    const [thinking, setThinking] = useState<string | null>(null);
    const [pendingUser, setPendingUser] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const started = useRef(false);

    const start = useCallback(async (fresh = false) => {
        setError(null);
        const id = fresh ? null : savedId();
        try {
            const loaded = id ? await api.conversation(id).catch(() => null) : null;
            const next = loaded ?? (await api.createConversation());
            remember(next.id);
            setState(next);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Сервер недоступен');
        }
    }, []);

    useEffect(() => {
        if (started.current) return;
        started.current = true;
        void start();
    }, [start]);

    // диалог у живого менеджера: его ответы приходят без нашего сообщения — забираем их раз в несколько секунд
    const withHuman = state?.handoff?.status === 'waiting' || state?.handoff?.status === 'active';
    const conversationId = state?.id;
    useEffect(() => {
        if (!withHuman || !conversationId || busy) return;
        const timer = window.setInterval(() => {
            api.conversation(conversationId)
                .then((fresh) =>
                    setState((current) =>
                        current && (fresh.messages.length !== current.messages.length || fresh.handoff?.status !== current.handoff?.status) ? fresh : current,
                    ),
                )
                .catch(() => undefined);
        }, 4000);
        return () => window.clearInterval(timer);
    }, [withHuman, conversationId, busy]);

    const send = useCallback(
        async (body: { text?: string; action?: Record<string, unknown> }, label?: string) => {
            if (!state || busy) return;
            setBusy(true);
            setError(null);
            setLiveSteps([]);
            setThinking('Думаю');
            setPendingUser(body.text ?? label ?? null);
            const payload = body.action && label ? { action: { ...body.action, label } } : body;
            try {
                await streamTurn(state.id, payload, (event) => {
                    if (event.type === 'step') {
                        setLiveSteps((steps) => [...steps, event.step]);
                        setThinking(null);
                    } else if (event.type === 'thinking') setThinking(event.title);
                    else if (event.type === 'state') setState(event.state);
                });
            } catch (e) {
                setError(e instanceof Error ? e.message : 'Связь с агентом прервалась');
            } finally {
                setBusy(false);
                setThinking(null);
                setPendingUser(null);
                setLiveSteps([]);
            }
        },
        [state, busy],
    );

    return { state, setState, busy, liveSteps, thinking, pendingUser, error, send, restart: () => start(true) };
}
