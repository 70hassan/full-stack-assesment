export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60)
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`
}

export const formatMiles = (miles: number) =>
  `${miles >= 100 ? Math.round(miles).toLocaleString() : miles.toFixed(miles % 1 ? 1 : 0)} mi`

const formatters = new Map<string, Intl.DateTimeFormat>()

function formatter(timeZone: string | undefined, style: 'full' | 'short'): Intl.DateTimeFormat {
  const key = `${timeZone}|${style}`
  let f = formatters.get(key)
  if (!f) {
    const options: Intl.DateTimeFormatOptions = {
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short',
      ...(style === 'full' ? { weekday: 'short', month: 'short', day: 'numeric' } : { weekday: 'short' }),
    }
    try {
      f = new Intl.DateTimeFormat('en-US', { ...options, timeZone })
    } catch {
      f = new Intl.DateTimeFormat('en-US', options) // unknown zone: fall back to the browser's
    }
    formatters.set(key, f)
  }
  return f
}

/** A moment shown in the local time of the place it refers to, e.g. "Fri, Nov 20, 3:10 PM MST". */
export const formatTime = (iso: string | Date, timeZone?: string, style: 'full' | 'short' = 'full') =>
  formatter(timeZone, style).format(typeof iso === 'string' ? new Date(iso) : iso)

export const formatNumber = (value: number | null | undefined, digits = 0) =>
  value == null ? '–' : value.toFixed(digits)

/** Value for an <input type="datetime-local"> in the browser's time zone. */
export function toLocalInputValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const WEATHER_CODES: [number, string][] = [
  [0, 'Clear'], [1, 'Mostly clear'], [2, 'Partly cloudy'], [3, 'Overcast'], [45, 'Fog'], [48, 'Freezing fog'],
  [51, 'Light drizzle'], [53, 'Drizzle'], [55, 'Heavy drizzle'], [56, 'Freezing drizzle'], [57, 'Freezing drizzle'],
  [61, 'Light rain'], [63, 'Rain'], [65, 'Heavy rain'], [66, 'Freezing rain'], [67, 'Freezing rain'],
  [71, 'Light snow'], [73, 'Snow'], [75, 'Heavy snow'], [77, 'Snow grains'], [80, 'Rain showers'],
  [81, 'Rain showers'], [82, 'Violent showers'], [85, 'Snow showers'], [86, 'Heavy snow showers'],
  [95, 'Thunderstorm'], [96, 'Thunderstorm, hail'], [99, 'Thunderstorm, hail'],
]
const codeNames = new Map(WEATHER_CODES)
export const describeWeather = (code: number | null | undefined) => (code == null ? '' : codeNames.get(code) ?? '')
