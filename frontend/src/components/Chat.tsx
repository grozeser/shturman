import { useEffect, useRef, useState } from 'react';
import type { Message, Quick, Step } from '../types';
import Icon, { type IconName } from './Icon';
import './Handoff.css';

const TOOL_ICONS: Record<string, IconName> = {
    update_brief: 'edit',
    infer_requirements: 'sparkle',
    search_destinations: 'compass',
    search_transport: 'plane',
    pick_dates: 'calendar',
    weather_forecast: 'sun',
    search_hotels: 'bed',
    assemble_trip: 'suitcase',
    validate_itinerary: 'check',
    replan: 'refresh',
    clarify: 'question',
    select_destination: 'pin',
    compare_destinations: 'swap',
    swap_component: 'swap',
    find_hacks: 'sparkle',
    apply_hack: 'wrench',
    apply_fix: 'wrench',
    add_to_cart: 'cart',
    check_kitchen: 'meal',
    post_purchase: 'ticket',
    answer_question: 'info',
    remember_preference: 'person',
    handoff: 'person',
    search_catalog: 'search',
    checkout: 'card',
    time_saved: 'sparkle',
};

function Steps({ steps, open: initiallyOpen, live }: { steps: Step[]; open: boolean; live?: boolean }) {
    const [open, setOpen] = useState(initiallyOpen);
    useEffect(() => {
        setOpen(initiallyOpen);
    }, [initiallyOpen]);
    if (!steps.length) return null;
    return (
        <div className={`steps ${live ? 'live' : ''}`}>
            <button className="steps-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
                {live ? 'Работаю' : 'Что я сделал'} · {steps.length} {steps.length === 1 ? 'шаг' : steps.length < 5 ? 'шага' : 'шагов'}
                <span className="chev">
                    <Icon name="chevron" size={16} />
                </span>
            </button>
            {open && (
                <ol>
                    {steps.map((step, index) => (
                        <li key={index} style={{ animationDelay: `${index * 70}ms` }}>
                            <span className="tool">
                                <Icon name={TOOL_ICONS[step.tool] ?? 'sparkle'} size={16} />
                            </span>
                            <div>
                                <b>{step.title}</b>
                                {step.detail && <span>{step.detail}</span>}
                            </div>
                            <code>{step.tool}</code>
                        </li>
                    ))}
                </ol>
            )}
        </div>
    );
}

type Recognition = { lang: string; interimResults: boolean; onresult: (e: { results: { 0: { transcript: string } }[] }) => void; onend: () => void; start: () => void; stop: () => void };

function useVoice(onText: (text: string) => void) {
    const [listening, setListening] = useState(false);
    const ref = useRef<Recognition | null>(null);
    const Ctor = (window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition }).SpeechRecognition
        ?? (window as unknown as { webkitSpeechRecognition?: new () => Recognition }).webkitSpeechRecognition;
    const toggle = () => {
        if (!Ctor) return;
        if (listening) {
            ref.current?.stop();
            return;
        }
        const recognition = new Ctor();
        recognition.lang = 'ru-RU';
        recognition.interimResults = false;
        recognition.onresult = (event) => onText(Array.from(event.results).map((r) => r[0].transcript).join(' '));
        recognition.onend = () => setListening(false);
        ref.current = recognition;
        setListening(true);
        recognition.start();
    };
    return { supported: Boolean(Ctor), listening, toggle };
}

const EXAMPLES = [
    'Хочу к тёплому морю в ноябре, недорого, с ребёнком 5 лет, без долгих перелётов',
    'Сочи с 10 по 17 ноября вдвоём, бюджет 80 тысяч',
    'На новый год покататься на лыжах компанией из 4 человек',
    'Из Казани в Турцию на майские с женой и собакой, всё включено',
    'Романтические выходные в городе с хорошей едой, на поезде',
];

export default function Chat(props: {
    messages: Message[];
    busy: boolean;
    liveSteps: Step[];
    thinking: string | null;
    pendingUser: string | null;
    onSend: (body: { text?: string; action?: Record<string, unknown> }, label?: string) => void;
}) {
    const { messages, busy, liveSteps, thinking, pendingUser, onSend } = props;
    const [text, setText] = useState('');
    const end = useRef<HTMLDivElement>(null);
    const voice = useVoice((spoken) => setText((current) => (current ? `${current} ${spoken}` : spoken)));
    const mounted = useRef(false);
    useEffect(() => {
        end.current?.scrollIntoView({ behavior: mounted.current ? 'smooth' : 'auto', block: 'end' });
        mounted.current = true;
    }, [messages.length, liveSteps.length, pendingUser]);
    const lastAgent = [...messages].reverse().find((m) => m.role === 'agent');
    const submit = () => {
        const value = text.trim();
        if (!value || busy) return;
        setText('');
        onSend({ text: value });
    };
    const press = (quick: Quick) => (quick.action ? onSend({ action: quick.action }, quick.label) : onSend({ text: quick.text ?? quick.label }));

    return (
        <div className="chat">
            <div className="messages" aria-live="polite">
                {messages.map((message) => (
                    <div key={message.id} className={`msg ${message.role} ${message.kind ?? ''}`}>
                        {message.role === 'agent' && message.steps && <Steps steps={message.steps} open={message === lastAgent && message.steps.length < 9} />}
                        {message.role === 'operator' && (
                            <span className="msg-author">
                                <Icon name="person" size={14} /> {message.author}, менеджер
                            </span>
                        )}
                        <div className="bubble">{message.text}</div>
                    </div>
                ))}
                {messages.length <= 1 && !busy && (
                    <div className="examples">
                        <span>Попробуйте:</span>
                        {EXAMPLES.map((example) => (
                            <button key={example} onClick={() => onSend({ text: example })}>
                                <span>{example}</span>
                                <Icon name="chevron" size={18} />
                            </button>
                        ))}
                    </div>
                )}
                {pendingUser && (
                    <div className="msg user">
                        <div className="bubble">{pendingUser}</div>
                    </div>
                )}
                {busy && (
                    <div className="msg agent">
                        <Steps steps={liveSteps} open live />
                        <div className="bubble typing">
                            <span className="dots">
                                <i />
                                <i />
                                <i />
                            </span>
                            {thinking ?? 'Собираю'}…
                        </div>
                    </div>
                )}
                <div ref={end} />
            </div>
            {!busy && lastAgent?.quick && lastAgent.quick.length > 0 && (
                <div className="quick">
                    {lastAgent.quick.map((quick) => (
                        <button key={quick.label} onClick={() => press(quick)}>
                            {quick.label}
                        </button>
                    ))}
                </div>
            )}
            <form
                className="composer"
                onSubmit={(event) => {
                    event.preventDefault();
                    submit();
                }}
            >
                <textarea
                    value={text}
                    rows={1}
                    placeholder="Опишите поездку своими словами…"
                    onChange={(event) => setText(event.target.value)}
                    onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                            event.preventDefault();
                            submit();
                        }
                    }}
                    aria-label="Сообщение агенту"
                />
                {voice.supported && (
                    <button type="button" className={`icon ${voice.listening ? 'rec' : ''}`} onClick={voice.toggle} aria-label="Голосовой ввод" title="Голосовой ввод">
                        <Icon name="mic" />
                    </button>
                )}
                <button type="submit" className="send" disabled={busy || !text.trim()} aria-label="Отправить">
                    <Icon name="send" />
                </button>
            </form>
        </div>
    );
}
