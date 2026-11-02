import { DEST_PHOTOS, HOTEL_PHOTOS } from '../photos';
import type { Hotel } from '../types';
import Scene, { type SceneProps } from './Scene';

function hash(text: string): number {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
    return h >>> 0;
}

export type HotelPhotoItem = (typeof HOTEL_PHOTOS)['resort'][number];

function hotelKind(hotel: Pick<Hotel, 'beach_m'>, kinds: string[]): keyof typeof HOTEL_PHOTOS {
    if (kinds.includes('ski')) return 'mountain';
    if (hotel.beach_m !== null) return 'resort';
    return kinds.includes('mountains') && !kinds.includes('city') ? 'mountain' : 'city';
}

/**
 * Раздаёт иллюстрации отелей карточкам одного экрана: каждый вызов — следующее ещё не показанное фото
 * подходящего типа (у моря — курорт, горнолыжное направление — горы, иначе — город). Фото на экране
 * не повторяются, даже если два варианта ведут в один отель; пул кончился — null, карточка без фото.
 */
export function hotelPhotoPicker(seed: string, kinds: string[] = []) {
    const used: Record<keyof typeof HOTEL_PHOTOS, number> = { resort: 0, city: 0, mountain: 0 };
    const start = hash(seed);
    return (hotel: Pick<Hotel, 'beach_m'>, hotelKinds: string[] = kinds): HotelPhotoItem | null => {
        const kind = hotelKind(hotel, hotelKinds);
        const pool = HOTEL_PHOTOS[kind];
        if (used[kind] >= pool.length) return null;
        return pool[(start + used[kind]++) % pool.length];
    };
}

/** Фото для карточки отеля. Отели в демо синтетические, поэтому снимок иллюстративный, и это написано прямо на фото. */
export function HotelPhoto({ photo, height }: { photo: HotelPhotoItem | null | undefined; height?: number }) {
    if (!photo) return null;
    return (
        <figure className="cover hotel-photo" style={{ height }}>
            <img src={`/photos/hotel/${photo.file}`} alt="" loading="lazy" decoding="async" />
            <span className="photo-note" title={`Отели в демо синтетические, фото не этого отеля. ${photo.author}, ${photo.license}, Wikimedia Commons`}>
                фото для примера
            </span>
        </figure>
    );
}

/**
 * Обложка направления: настоящее фото с Wikimedia Commons (свободные лицензии, автор — в подписи),
 * а для мест вне каталога, найденных на карте, — нарисованная сцена по погоде.
 * credit="text" — подпись без ссылки, когда обложка уже внутри ссылки (карточка поездки).
 */
export default function Cover({ dest, credit = 'link', ...scene }: SceneProps & { dest: string; credit?: 'link' | 'text' }) {
    const photo = DEST_PHOTOS[dest];
    if (!photo) return <Scene {...scene} />;
    const label = `Фото: ${photo.author}, ${photo.license}, Wikimedia Commons`;
    return (
        <figure className="cover" style={{ height: scene.height }}>
            <img src={`/photos/dest/${dest}.webp`} alt={scene.title ?? ''} loading="lazy" decoding="async" />
            {credit === 'link' ? (
                <a className="photo-credit" href={photo.source} target="_blank" rel="noreferrer" title={label}>
                    © {photo.author}
                </a>
            ) : (
                <span className="photo-credit" title={label}>
                    © {photo.author}
                </span>
            )}
        </figure>
    );
}
