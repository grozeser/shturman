/**
 * Обложка направления, нарисованная кодом: море, горы, город или природа — по типу отдыха,
 * а солнце, тучи и снег — по реальной погоде месяца. Оттенки зависят от направления, поэтому обложки не одинаковые.
 */

export interface SceneProps {
    seed: string;
    kinds: string[];
    air?: number | null;
    water?: number | null;
    rain?: number | null;
    height?: number;
    title?: string;
}

function hash(text: string): number {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
    return h >>> 0;
}

function rand(seed: number) {
    let s = seed || 1;
    return () => {
        s = Math.imul(s ^ (s >>> 15), 2246822507) ^ Math.imul(s ^ (s >>> 13), 3266489909);
        return ((s ^= s >>> 16) >>> 0) / 4294967296;
    };
}

type Kind = 'sea' | 'ski' | 'mountains' | 'city' | 'nature';

function mainKind(kinds: string[]): Kind {
    if (kinds.includes('sea')) return 'sea';
    if (kinds.includes('ski')) return 'ski';
    if (kinds.includes('mountains')) return 'mountains';
    if (kinds.includes('city') || kinds.includes('culture')) return 'city';
    return 'nature';
}

export default function Scene({ seed, kinds, air = null, water = null, rain = null, height = 120, title }: SceneProps) {
    const r = rand(hash(seed));
    const kind = mainKind(kinds);
    const cold = air !== null && air <= 3;
    const hot = (air ?? 20) >= 26 || (water ?? 0) >= 25;
    const rainy = (rain ?? 0) >= 10;
    const hue = Math.round(r() * 40) - 20; // свой оттенок у каждого направления
    const id = `s${hash(seed).toString(36)}`;
    const sky = rainy ? ['#9fb4c4', '#d6e0e6'] : cold ? ['#a9c7e8', '#eef4fb'] : hot ? ['#ffb37a', '#ffe7c2'] : ['#7ec8f0', '#d9f1ff'];
    const sunX = 60 + r() * 280;
    const exotic = kinds.includes('exotic') || hot;

    const layers: JSX.Element[] = [];
    if (kind === 'sea') {
        const sea = (water ?? 22) >= 24 ? ['#19b5c4', '#0d7f99'] : ['#3c8fc0', '#255f8a'];
        layers.push(
            <rect key="sea" x="0" y="96" width="400" height="64" fill={`url(#${id}-sea)`} />,
            <defs key="sea-g">
                <linearGradient id={`${id}-sea`} x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0" stopColor={sea[0]} />
                    <stop offset="1" stopColor={sea[1]} />
                </linearGradient>
            </defs>,
        );
        for (let i = 0; i < 4; i++) {
            const y = 104 + i * 11;
            layers.push(<path key={`w${i}`} d={`M0 ${y} q 25 -5 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0 t 50 0`} stroke="rgba(255,255,255,.35)" strokeWidth="1.6" fill="none" />);
        }
        layers.push(<path key="beach" d="M230 160 Q 300 118 400 124 L400 160 Z" fill="#f1d9a5" />);
        if (exotic) {
            const px = 330 + r() * 30;
            layers.push(
                <g key="palm" stroke="#2f5d3a" strokeLinecap="round">
                    <path d={`M${px} 132 q -4 -30 6 -58`} strokeWidth="4" fill="none" stroke="#7a5532" />
                    {[-60, -25, 10, 45, 80].map((a) => (
                        <path key={a} d={`M${px + 6} 74 q ${Math.cos((a * Math.PI) / 180) * 22} ${Math.sin((a * Math.PI) / 180) * 10 - 8} ${Math.cos((a * Math.PI) / 180) * 34} ${Math.sin((a * Math.PI) / 180) * 18 + 6}`} strokeWidth="5" fill="none" />
                    ))}
                </g>,
            );
        }
        layers.push(<path key="boat" d={`M${80 + r() * 100} 100 l 22 0 l -4 6 l -14 0 z`} fill="#fff" opacity=".85" />);
    } else if (kind === 'ski' || kind === 'mountains') {
        const peaks = [0, 1, 2, 3].map((i) => ({ x: i * 120 - 20 + r() * 50, h: 60 + r() * 50 }));
        peaks.forEach((p, i) => {
            const base = 150;
            const top = base - p.h - 30;
            layers.push(
                <g key={`p${i}`}>
                    <path d={`M${p.x - 90} ${base} L${p.x} ${top} L${p.x + 90} ${base} Z`} fill={i % 2 ? '#6b7f92' : '#58697b'} />
                    {(cold || kind === 'ski' || p.h > 90) && <path d={`M${p.x - 22} ${top + 26} L${p.x} ${top} L${p.x + 22} ${top + 26} l -8 -4 l -7 6 l -7 -6 z`} fill="#fff" />}
                </g>,
            );
        });
        layers.push(<rect key="ground" x="0" y="140" width="400" height="20" fill={cold || kind === 'ski' ? '#f4f8fb' : '#7fae6e'} />);
        for (let i = 0; i < 7; i++) {
            const x = r() * 400;
            layers.push(<path key={`t${i}`} d={`M${x} 150 l 8 -22 l 8 22 z`} fill="#2e5b45" />);
        }
    } else if (kind === 'city') {
        layers.push(<rect key="river" x="0" y="140" width="400" height="20" fill="#5aa0c8" />);
        let x = -10;
        let i = 0;
        while (x < 410) {
            const w = 26 + r() * 30;
            const h = 30 + r() * 70;
            const color = ['#3d5a80', '#4a6fa5', '#2f4858', '#56657a'][i % 4];
            layers.push(<rect key={`b${i}`} x={x} y={140 - h} width={w} height={h} fill={color} rx="2" />);
            for (let wy = 140 - h + 6; wy < 134; wy += 10) {
                for (let wx = x + 5; wx < x + w - 6; wx += 9) {
                    if (r() > 0.45) layers.push(<rect key={`win${i}-${wx}-${wy}`} x={wx} y={wy} width="4" height="5" fill="#ffe08a" opacity=".85" />);
                }
            }
            if (r() > 0.75) layers.push(<path key={`dome${i}`} d={`M${x + 4} ${140 - h} q ${w / 2 - 4} -22 ${w - 8} 0 z`} fill="#c9a24a" />);
            x += w + 2;
            i++;
        }
    } else {
        layers.push(<path key="hill" d="M0 120 Q 100 80 200 112 T 400 104 L400 160 L0 160 Z" fill="#6fa46a" />);
        layers.push(<ellipse key="lake" cx={130 + r() * 140} cy="142" rx="90" ry="12" fill="#5aa0c8" />);
        for (let i = 0; i < 12; i++) {
            const tx = r() * 400;
            const ty = 112 + r() * 22;
            layers.push(<path key={`f${i}`} d={`M${tx} ${ty + 22} l 9 -26 l 9 26 z`} fill={i % 2 ? '#2e5b45' : '#3d7357'} />);
        }
    }

    return (
        <svg className="scene" viewBox="0 0 400 160" preserveAspectRatio="xMidYMid slice" style={{ height, filter: `hue-rotate(${hue}deg)` }} role="img" aria-label={title ?? 'Иллюстрация направления'}>
            <defs>
                <linearGradient id={`${id}-sky`} x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0" stopColor={sky[0]} />
                    <stop offset="1" stopColor={sky[1]} />
                </linearGradient>
            </defs>
            <rect width="400" height="160" fill={`url(#${id}-sky)`} />
            {!rainy && <circle cx={sunX} cy={34} r={hot ? 20 : 15} fill={hot ? '#fff3b0' : '#fffbe0'} opacity=".95" />}
            {(rainy || r() > 0.5) &&
                [0, 1, 2].map((i) => {
                    const cx = 40 + i * 130 + r() * 40;
                    return (
                        <g key={`c${i}`} fill={rainy ? '#eef2f5' : '#fff'} opacity={rainy ? 0.95 : 0.8}>
                            <ellipse cx={cx} cy={30 + i * 6} rx="26" ry="10" />
                            <ellipse cx={cx + 16} cy={24 + i * 6} rx="16" ry="10" />
                        </g>
                    );
                })}
            {layers}
            {rainy &&
                Array.from({ length: 26 }, (_, i) => <line key={`r${i}`} x1={(i * 37) % 400} y1={44 + (i % 5) * 8} x2={(i * 37) % 400 - 4} y2={56 + (i % 5) * 8} stroke="rgba(255,255,255,.6)" />)}
            {cold && Array.from({ length: 24 }, (_, i) => <circle key={`n${i}`} cx={(i * 53) % 400} cy={(i * 29) % 140} r="1.8" fill="#fff" opacity=".9" />)}
        </svg>
    );
}
