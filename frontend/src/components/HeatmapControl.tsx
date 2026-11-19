import { formatTime } from '../lib/format'
import { METRICS } from '../lib/risk'
import type { Heatmap, Metric } from '../lib/types'

interface Props {
  heatmap: Heatmap | null
  /** Zone for the time label: the origin's, so it matches the departure time shown. */
  timeZone?: string
  loading: boolean
  error: string
  visible: boolean
  onVisibleChange: (visible: boolean) => void
  metric: Metric
  onMetricChange: (metric: Metric) => void
  hour: number
  onHourChange: (hour: number) => void
  playing: boolean
  onPlayingChange: (playing: boolean) => void
}

const METRIC_ORDER: Metric[] = ['risk', 'wind', 'rain', 'snow']

export default function HeatmapControl(props: Props) {
  const { heatmap, timeZone, loading, error, visible, onVisibleChange, metric, onMetricChange, hour, onHourChange, playing, onPlayingChange } = props
  const scale = METRICS[metric]
  const hours = heatmap?.hours ?? 48
  const max = scale.stops[scale.stops.length - 1][0]
  const gradient = scale.stops.map(([value, color]) => `${color} ${(value / max) * 100}%`).join(', ')
  const moment = heatmap ? new Date(new Date(heatmap.start_time).getTime() + Math.round(hour) * 3600_000) : null
  const disabled = !heatmap || !visible

  return (
    <section className="heat-control" aria-label="Weather heatmap">
      <div className="heat-top">
        <label className="switch">
          <input type="checkbox" checked={visible} onChange={(e) => onVisibleChange(e.target.checked)} />
          <span className="track" aria-hidden />
          <strong>Corridor weather</strong>
        </label>
        <div className="segmented small" role="radiogroup" aria-label="Heatmap layer">
          {METRIC_ORDER.map((key) => (
            <button key={key} type="button" role="radio" aria-checked={metric === key} className={metric === key ? 'on' : ''} disabled={!visible} onClick={() => onMetricChange(key)}>
              {METRICS[key].label}
            </button>
          ))}
        </div>
        <div className="heat-legend" aria-hidden={!visible}>
          <div className="ramp" style={{ background: `linear-gradient(to right, ${gradient})` }} />
          <div className="ticks">
            {scale.ticks.map((tick) => (
              <span key={tick.value} style={{ left: `${(tick.value / max) * 100}%` }}>{tick.label}</span>
            ))}
          </div>
          {scale.unit && <span className="unit">{scale.unit}</span>}
        </div>
      </div>

      <div className="heat-bottom">
        <button type="button" className="play" disabled={disabled} onClick={() => onPlayingChange(!playing)} aria-label={playing ? 'Pause forecast animation' : 'Play forecast animation'}>
          {playing ? '❚❚' : '▶'}
        </button>
        <div className="slider">
          <input
            type="range"
            min={0}
            max={hours}
            step={1}
            value={Math.round(hour)}
            disabled={disabled}
            aria-label="Hours after departure"
            aria-valuetext={`${Math.round(hour)} hours after departure`}
            onChange={(e) => {
              onPlayingChange(false)
              onHourChange(Number(e.target.value))
            }}
          />
          <div className="slider-ticks" aria-hidden>
            {[0, 12, 24, 36, 48].filter((t) => t <= hours).map((t) => (
              <span key={t} style={{ left: `${(t / hours) * 100}%` }}>+{t}h</span>
            ))}
          </div>
        </div>
        <output className="heat-time">
          {loading && <><span className="spinner small" aria-hidden /> Loading forecast…</>}
          {!loading && error && <span className="heat-error">{error}</span>}
          {!loading && !error && moment && (
            <>
              <strong>+{Math.round(hour)} h</strong>
              <span>{formatTime(moment, timeZone)}</span>
            </>
          )}
          {!loading && !error && !moment && <span>Plan a trip to load the forecast</span>}
        </output>
      </div>
    </section>
  )
}
