import { useState, type FormEvent } from 'react'
import { searchPlaces } from '../lib/api'
import { toLocalInputValue } from '../lib/format'
import type { Place, TripRequest } from '../lib/types'
import PlaceInput from './PlaceInput'

export const INTERVALS = [10, 25, 50]
const LOAD_PRESETS = [
  { label: 'Empty', value: 0 },
  { label: '20k', value: 20000 },
  { label: '35k', value: 35000 },
  { label: '45k', value: 45000 },
]
const MAX_DAYS_AHEAD = 10

interface Props {
  busy: boolean
  interval: number
  onIntervalChange: (interval: number) => void
  onSubmit: (trip: TripRequest) => void
}

const defaultDeparture = () => {
  const date = new Date(Date.now() + 60 * 60 * 1000)
  date.setMinutes(0, 0, 0)
  return toLocalInputValue(date)
}

export default function TripForm({ busy, interval, onIntervalChange, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>({ label: 'Denver, Colorado, US', lat: 39.73915, lon: -104.9847 })
  const [destination, setDestination] = useState<Place | null>({ label: 'Salt Lake City, Utah, US', lat: 40.76078, lon: -111.89105 })
  const [originText, setOriginText] = useState(origin?.label ?? '')
  const [destinationText, setDestinationText] = useState(destination?.label ?? '')
  const [departure, setDeparture] = useState(defaultDeparture)
  const [load, setLoad] = useState('42000')
  const [error, setError] = useState('')
  const [resolving, setResolving] = useState(false)

  const now = new Date()
  const minDeparture = toLocalInputValue(now)
  const maxDeparture = toLocalInputValue(new Date(now.getTime() + MAX_DAYS_AHEAD * 86400_000))

  // If the driver typed a place without picking a suggestion, use the best match.
  const resolve = async (place: Place | null, text: string, what: string) => {
    if (place) return place
    if (text.trim().length < 2) throw new Error(`Enter ${what}.`)
    const [first] = await searchPlaces(text)
    if (!first) throw new Error(`Could not find "${text.trim()}". Try a city name such as "Dallas, TX".`)
    return first
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    const weight = Number(load)
    if (!departure) return setError('Choose a departure date and time.')
    if (load.trim() === '' || !Number.isFinite(weight) || weight < 0) return setError('Enter the load weight in pounds.')
    if (weight > 200000) return setError('Load weight must be 200,000 lb or less.')
    try {
      setResolving(true)
      const from = await resolve(origin, originText, 'an origin')
      const to = await resolve(destination, destinationText, 'a destination')
      setOrigin(from)
      setDestination(to)
      onSubmit({
        origin: from,
        destination: to,
        departure_time: new Date(departure).toISOString(),
        load_weight_lb: Math.round(weight),
        interval_miles: interval,
      })
    } catch (problem) {
      setError((problem as Error).message)
    } finally {
      setResolving(false)
    }
  }

  const swap = () => {
    setOrigin(destination)
    setDestination(origin)
    setOriginText(destinationText)
    setDestinationText(originText)
  }

  return (
    <form className="trip-form" onSubmit={submit} noValidate>
      <div className="places">
        <PlaceInput label="Origin" placeholder="City, e.g. Denver, CO" value={origin} onChange={setOrigin} onTextChange={setOriginText} />
        <button type="button" className="swap" onClick={swap} title="Swap origin and destination" aria-label="Swap origin and destination">
          ⇅
        </button>
        <PlaceInput label="Destination" placeholder="City, e.g. Salt Lake City, UT" value={destination} onChange={setDestination} onTextChange={setDestinationText} />
      </div>

      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure <span className="soft">(your local time)</span></label>
          <input id="departure" type="datetime-local" value={departure} min={minDeparture} max={maxDeparture} onChange={(e) => setDeparture(e.target.value)} />
        </div>
        <div className="field load">
          <label htmlFor="load">Load weight</label>
          <div className="suffix">
            <input id="load" type="number" inputMode="numeric" min={0} max={200000} step={500} value={load} onChange={(e) => setLoad(e.target.value)} />
            <span>lb</span>
          </div>
        </div>
      </div>

      <div className="presets" aria-label="Load weight presets">
        {LOAD_PRESETS.map((preset) => (
          <button key={preset.value} type="button" className={Number(load) === preset.value && load !== '' ? 'on' : ''} onClick={() => setLoad(String(preset.value))}>
            {preset.label}
          </button>
        ))}
        <span className="hint">Wind rules tighten above 30,000 and 40,000 lb</span>
      </div>

      <div className="field">
        <span className="label" id="interval-label">Sample weather every</span>
        <div className="segmented" role="radiogroup" aria-labelledby="interval-label">
          {INTERVALS.map((miles) => (
            <button key={miles} type="button" role="radio" aria-checked={interval === miles} className={interval === miles ? 'on' : ''} onClick={() => onIntervalChange(miles)}>
              {miles} mi
            </button>
          ))}
        </div>
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}

      <button type="submit" className="primary" disabled={busy || resolving}>
        {busy || resolving ? <><span className="spinner small light" aria-hidden /> Planning…</> : 'Find the safest route'}
      </button>
    </form>
  )
}
