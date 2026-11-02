import { day, plural, temp } from '../format';
import type { Forecast } from '../types';
import Icon from './Icon';
import './ForecastCard.css';

const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

// Настоящий прогноз на даты поездки: по дням, с дождливыми днями и советом, что перенести
export default function ForecastCard({ forecast, norm }: { forecast: Forecast; norm?: number | null }) {
    const partial = forecast.covered < forecast.total;
    return (
        <section className="card forecast" aria-labelledby="forecast-title">
            <header>
                <h2 id="forecast-title">Прогноз на ваши даты</h2>
                <span className="muted">
                    {forecast.source}
                    {partial ? ` · ${forecast.covered} ${plural(forecast.covered, 'день', 'дня', 'дней')} из ${forecast.total}, дальше прогноз пока не заглядывает` : ''}
                    {norm !== null && norm !== undefined ? ` · норма месяца днём ${temp(norm)}` : ''}
                </span>
            </header>
            {forecast.advice && (
                <p className={`forecast-advice${forecast.rainy.length ? ' wet' : ''}`}>
                    <Icon name={forecast.rainy.length ? 'umbrella' : 'sun'} size={16} /> {forecast.advice}
                </p>
            )}
            <ol className="forecast-days" aria-label="Прогноз по дням">
                {forecast.days.map((d) => (
                    <li key={d.date} className={d.rainy ? 'rainy' : ''} title={d.sky}>
                        <small>
                            {WEEKDAYS[new Date(`${d.date}T12:00:00`).getDay()]}, {day(d.date)}
                        </small>
                        <Icon name={d.rainy || d.rain_mm >= 1 ? 'umbrella' : 'sun'} size={18} />
                        <b>{temp(d.tmax)}</b>
                        <span>{temp(d.tmin)}</span>
                        <span className="forecast-rain">{d.rain_mm >= 1 ? `${String(d.rain_mm).replace('.', ',')} мм` : d.sky}</span>
                    </li>
                ))}
            </ol>
        </section>
    );
}
