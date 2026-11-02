export interface Step {
    tool: string;
    title: string;
    detail: string;
    ms: number;
}

export interface Quick {
    label: string;
    text?: string;
    action?: Record<string, unknown>;
}

export interface Message {
    id: string;
    role: 'user' | 'agent' | 'operator';
    author?: string;
    text: string;
    kind?: string;
    quick?: Quick[];
    steps?: Step[];
}

export interface Chip {
    key: string;
    label: string;
    kind: 'explicit' | 'inferred' | 'memory' | 'default';
    reason: string;
}

export interface Transport {
    id: string;
    mode: 'flight' | 'train' | 'bus' | 'car';
    carrier: string;
    number: string;
    from: string;
    to: string;
    depart: string;
    arrive: string;
    duration_min: number;
    stops: number;
    via: string | null;
    layover_min: number;
    night: boolean;
    baggage: boolean;
    pets_cabin: boolean;
    class: string;
    price: number;
    cost?: number;
    included?: boolean;
}

export interface Hotel {
    id: string;
    name: string;
    stars: number;
    rating: number;
    reviews: number;
    area: string;
    beach_m: number | null;
    center_km: number;
    airport_km: number;
    checkin: string;
    checkout: string;
    features: Record<string, boolean>;
    meals: string[];
    diets?: string[];
    meal: string;
    meal_label: string;
    refundable: boolean;
    free_cancel_until: string | null;
    price_total: number;
    price_night: number;
    fit: number;
    value?: number;
    pros: string[];
    cons: string[];
    not_for: string[];
}

export interface Transfer {
    id: string;
    kind: 'shuttle' | 'taxi' | 'private' | 'accessible';
    title: string;
    price: number;
    duration_min: number;
    child_seat: boolean;
}

export interface Check {
    id: string;
    status: 'ok' | 'warn' | 'error' | 'fixed';
    title: string;
    detail: string;
    fix: null | { type: string; label: string; price: number };
}

export interface Bundle {
    id: string;
    label: string;
    style: 'best' | 'cheap' | 'comfort';
    dest: string;
    dest_name: string;
    dest_info?: {
        country: string;
        kinds: string[];
        weather: { air: number | null; water: number | null; rain: number | null };
        visa: string;
        dynamic: boolean;
        lat?: number;
        lon?: number;
        origin?: { name: string; lat: number; lon: number };
    };
    checkin: string;
    checkout: string;
    nights: number;
    outbound: Transport;
    inbound: Transport;
    hotel: Hotel;
    transfer_in: Transfer;
    transfer_out: Transfer;
    extras: { type: string; title: string; price: number }[];
    costs: Record<'transport' | 'hotel' | 'meals' | 'transfers' | 'extras', number>;
    total: number;
    per_person: number;
    fit: number;
    why: string[];
    sacrifices: string[];
    risks: string[];
    checks: Check[];
    caught?: { kind: 'fixed' | 'trap' | 'filtered'; title: string; detail: string }[];
    hacks?: { kind: string; title: string; detail: string; saving: number | null; action: Record<string, unknown> | null; label: string | null }[];
    legs?: Bundle[];
}

export interface Plan {
    multi?: boolean;
    dest: string;
    checkin: string;
    checkout: string;
    nights: number;
    dates_how: string;
    date_scan: { date: string; estimate: number }[];
    bundles: Bundle[];
    hotels: Hotel[];
    hotels_rejected: { id: string; name: string; stars: number; rating: number; reason: string }[];
    outbound: Transport[];
    inbound: Transport[];
    relaxed: string[];
    downgrade: { text: string; saving: number }[];
    forecast?: Forecast;
}

/** Настоящий прогноз Open-Meteo на даты поездки (если она в ближайшие 16 дней). */
export interface Forecast {
    source: string;
    days: { date: string; tmax: number; tmin: number; rain_mm: number; rain_prob: number | null; code: number | null; sky: string; rainy: boolean }[];
    covered: number;
    total: number;
    tmax: [number, number];
    rainy: string[];
    advice: string | null;
    line: string;
}

export interface Destination {
    id: string;
    name: string;
    country: string;
    why: string[];
    cons: string[];
    highlights: string[];
    weather: { air: number | null; water: number | null; rain: number | null };
    travel: { mode: string; minutes: number; stops: number };
    visa: string;
    price_from: number;
    price_mid: number;
    kinds: string[];
}

/** «Сколько времени вы сэкономили»: что агент сравнил и проверил, и оценка ручного пути. */
export interface Savings {
    messages: number;
    taps: number;
    clicks: number;
    sites: number;
    minutes: number;
    destinations: number;
    hotels: number;
    transport: number;
    dates: number;
    checks: number;
    line: string;
}

export interface Diff {
    changes: { part: string; before: string; after: string; delta: number | null }[];
    kept: string[];
    total_before: number;
    total_after: number;
    delta: number;
    same_hotel: boolean;
}

/** «Турция или Египет?»: собранные поездки рядом. Поля поездки пустые, если её не собрать (error). */
export interface Comparison {
    items: {
        id: string;
        name: string;
        country: string;
        kinds: string[];
        visa: string;
        error: string | null;
        checkin?: string;
        checkout?: string;
        nights?: number;
        total?: number;
        per_person?: number;
        weather?: { air: number | null; water: number | null; rain: number | null };
        travel?: { mode: string; minutes: number; stops: number; via: string | null };
        hotel?: { name: string; stars: number; rating: number; meal_label: string; beach_m: number | null; fit: number };
        warnings?: string[];
        pros: string[];
        cons: string[];
    }[];
    winner: string | null;
    month: number | null;
    verdict: string;
}

export interface ConversationState {
    id: string;
    stage: 'start' | 'clarify' | 'inspire' | 'compare' | 'plan' | 'checkout' | 'booked';
    comparison?: Comparison | null;
    brief: Record<string, unknown> & { priorities: Record<string, number>; children: number[]; adults: number };
    chips: Chip[];
    suggestions: null | { month: number; checked: number; items: Destination[]; more: Destination[]; rejected: { id: string; name: string; reason: string }[] };
    plan: Plan | null;
    selected: number;
    handoff?: Handoff | null;
    diff: Diff | null;
    booking_id: string | null;
    documents?: { insurance: Policy; passport: PassportCheck | null; passport_check: PassportCheck | null } | null;
    checkout_options?: { insurance?: boolean };
    passport_until?: string | null;
    messages: Message[];
    metrics: Record<string, number | boolean | null>;
    llm: { enabled: boolean; model: string | null; mode: string };
    savings?: Savings | null;
}

/** Полис в корзине: цена на всех, покрытие и что входит. */
export interface Policy {
    title: string;
    coverage: string;
    price: number;
    per_person: number;
    days: number;
    people: number;
    includes: string[];
    required: boolean;
    insurer: string;
    number?: string;
}

/** Проверка загранпаспорта по правилам страны: до какого числа он должен действовать. */
export interface PassportCheck {
    country: string;
    required: string;
    rule: string;
    ok?: boolean;
    until?: string;
    text?: string;
}

export interface Booking {
    id: string;
    status: 'confirmed' | 'cancelled';
    created: string;
    traveller: { name: string; email: string };
    bundle: Bundle;
    brief: ConversationState['brief'];
    payment: { amount: number; status: string; method: string; refund?: number };
    insurance?: Policy;
    passport?: PassportCheck;
    services: { type: string; title: string; price: number; status: string }[];
    history: { ts: string; text: string }[];
    reminders: { at: string; text: string }[];
    forecast?: Forecast | null;
    pending: null | { type: string; extra?: number; refund?: number };
    requests?: { type: string; who: string; what: string; status: string }[];
    checklist?: { title: string; items: { text: string; why: string }[] }[];
    savings?: Savings;
}

/** Диалог у живого менеджера: ждёт ответа, менеджер на связи или обращение закрыто. */
export interface Handoff {
    status: 'waiting' | 'active' | 'closed';
    reason: string;
    since: number;
    updated: number;
    operator: string | null;
    unread: number;
}

export type StreamEvent =
    | { type: 'step'; step: Step }
    | { type: 'thinking'; title: string }
    | { type: 'message'; message: Message }
    | { type: 'state'; state: ConversationState };
