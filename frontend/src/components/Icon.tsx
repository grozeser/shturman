/**
 * Иконки интерфейса — линейные SVG 24×24 в цвете текста, вместо эмодзи.
 * Пути самолёта и ключа взяты из Lucide (ISC License, © Lucide Contributors), остальные нарисованы здесь.
 */

const PATHS = {
    search: (
        <>
            <circle cx="10.5" cy="10.5" r="6.5" />
            <path d="M15.5 15.5 20.5 20.5" />
        </>
    ),
    suitcase: (
        <>
            <rect x="3" y="7" width="18" height="13" rx="3" />
            <path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M8 7v13M16 7v13" />
        </>
    ),
    person: (
        <>
            <circle cx="12" cy="8" r="4" />
            <path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" />
        </>
    ),
    hotel: <path d="M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M16 9h2a2 2 0 0 1 2 2v10M3 21h18M8 7h4M8 11h4M8 15h4" />,
    chart: <path d="M4 20h16M7 16v-5M12 16V6M17 16V9" />,
    chat: <path d="M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1h-9l-5 4v-4H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" />,
    map: <path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14" />,
    send: <path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" />,
    mic: (
        <>
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
        </>
    ),
    plane: <path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z" />,
    train: (
        <>
            <rect x="5" y="3" width="14" height="14" rx="3" />
            <path d="M5 10h14M9 21l-2-4M15 21l2-4M9 13.5h.01M15 13.5h.01" />
        </>
    ),
    bus: (
        <>
            <rect x="4" y="3" width="16" height="15" rx="3" />
            <path d="M4 11h16M7 21v-3M17 21v-3M8 14.5h.01M16 14.5h.01" />
        </>
    ),
    car: (
        <>
            <path d="M5 17H3v-4l2-5a2 2 0 0 1 1.9-1.4h10.2A2 2 0 0 1 19 8l2 5v4h-2M3 13h18M9.5 17h5" />
            <circle cx="7.5" cy="17" r="2" />
            <circle cx="16.5" cy="17" r="2" />
        </>
    ),
    pin: (
        <>
            <path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z" />
            <circle cx="12" cy="9.5" r="2.5" />
        </>
    ),
    key: (
        <>
            <circle cx="7.5" cy="15.5" r="5.5" />
            <path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3" />
        </>
    ),
    sun: (
        <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </>
    ),
    wave: <path d="M2 7q2.5-3 5 0t5 0 5 0 5 0M2 12q2.5-3 5 0t5 0 5 0 5 0M2 17q2.5-3 5 0t5 0 5 0 5 0" />,
    umbrella: <path d="M3 12a9 9 0 0 1 18 0zM12 12v6.5a2.5 2.5 0 0 1-5 0" />,
    passport: (
        <>
            <rect x="5" y="3" width="14" height="18" rx="2" />
            <circle cx="12" cy="10" r="3" />
            <path d="M9 16h6" />
        </>
    ),
    bed: (
        <>
            <path d="M3 19V6M3 15h18v4M21 15v-3a3 3 0 0 0-3-3h-7v6" />
            <circle cx="7" cy="11" r="2" />
        </>
    ),
    meal: <path d="M7 3v18M4 3v5a3 3 0 0 0 6 0V3M17 21V3c-2 1.5-3 4-3 7v3h3" />,
    check: <path d="M5 12.5 9.5 17 19 7.5" />,
    warn: <path d="M12 6v8M12 18.5v.01" />,
    close: <path d="M6 6l12 12M18 6 6 18" />,
    wrench: <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9z" />,
    chevron: <path d="M9 5l7 7-7 7" />,
    sparkle: <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7z" />,
    compass: (
        <>
            <circle cx="12" cy="12" r="9" />
            <path d="M15.5 8.5l-2 5-5 2 2-5z" />
        </>
    ),
    calendar: (
        <>
            <rect x="3" y="5" width="18" height="16" rx="3" />
            <path d="M3 10h18M8 3v4M16 3v4" />
        </>
    ),
    cart: (
        <>
            <path d="M3 4h2l2.4 11.2a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.5L21 8H6" />
            <circle cx="10" cy="20.5" r="1" />
            <circle cx="17" cy="20.5" r="1" />
        </>
    ),
    ticket: <path d="M4 6h16a1 1 0 0 1 1 1v3a2 2 0 0 0 0 4v3a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-3a2 2 0 0 0 0-4V7a1 1 0 0 1 1-1zM14 6v2M14 11v2M14 16v2" />,
    info: (
        <>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 11v5M12 8v.01" />
        </>
    ),
    question: (
        <>
            <circle cx="12" cy="12" r="9" />
            <path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17v.01" />
        </>
    ),
    edit: <path d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4" />,
    refresh: <path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v4.5h-4.5" />,
    swap: <path d="M7 4 3 8l4 4M3 8h14M17 12l4 4-4 4M21 16H7" />,
    card: (
        <>
            <rect x="3" y="5" width="18" height="14" rx="3" />
            <path d="M3 10h18M7 15h3" />
        </>
    ),
} satisfies Record<string, JSX.Element>;

export type IconName = keyof typeof PATHS;

export default function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
    return (
        <svg className="ico" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
            {PATHS[name]}
        </svg>
    );
}
