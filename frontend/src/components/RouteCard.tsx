import { formatDuration, formatMiles, formatNumber, formatTime } from '../lib/format'
import { LEVELS } from '../lib/risk'
import type { Checkpoint, RouteOption } from '../lib/types'

interface Props {
  route: RouteOption
  selected: boolean
  onSelect: () => void
  hovered: number | null
  onHover: (index: number | null) => void
  onFocus: (index: number) => void
  riskyOnly: boolean
  onRiskyOnlyChange: (value: boolean) => void
}

const worst = (route: RouteOption): Checkpoint | null => {
  let found: Checkpoint | null = null
  for (const cp of route.checkpoints) if (cp.risk.level > 0 && (!found || cp.risk.level > found.risk.level)) found = cp
  return found
}

function describeDrivers(cp: Checkpoint): string {
  if (!cp.weather) return ''
  const parts: string[] = []
  if (cp.risk.drivers.includes('wind')) parts.push(`wind ${formatNumber(cp.weather.wind_mph)} mph`)
  if (cp.risk.drivers.includes('rain')) parts.push(`rain ${formatNumber(cp.weather.rain_in_per_hr, 2)} in/hr`)
  if (cp.risk.drivers.includes('snow')) parts.push(`snow ${formatNumber(cp.weather.snow_in_per_hr, 2)} in/hr`)
  return parts.join(', ')
}

export default function RouteCard(props: Props) {
  const { route, selected, onSelect, hovered, onHover, onFocus, riskyOnly, onRiskyOnlyChange } = props
  const { summary } = route
  const peak = worst(route)
  const rows = riskyOnly ? route.checkpoints.filter((cp) => cp.risk.level > 0) : route.checkpoints
  const anyRisk = route.checkpoints.some((cp) => cp.risk.level > 0)

  return (
    <article className={`route-card${selected ? ' selected' : ''}${route.recommended ? ' recommended' : ''}`}>
      <button type="button" className="route-head" onClick={onSelect} aria-expanded={selected}>
        <span className="route-letter">{route.id}</span>
        <span className="route-title">
          <strong>{route.name ? `via ${route.name}` : `Route ${route.id}`}</strong>
          <span className="route-sub">
            {formatDuration(route.duration_seconds)} · {formatMiles(route.distance_miles)} · arrive {formatTime(route.arrival_time, route.arrival_timezone)}
          </span>
        </span>
        {route.recommended ? <span className="tag best">Recommended</span> : <span className="tag">#{route.rank}</span>}
      </button>

      {/* Risk along the route, start to finish: one block per checkpoint. */}
      <div className="strip" role="img" aria-label={`Risk along route ${route.id}, from origin to destination`}>
        {route.checkpoints.map((cp) => (
          <span
            key={cp.index}
            style={{ flexGrow: Math.max(0.01, cp.span.to_mile - cp.span.from_mile), background: LEVELS[cp.risk.level].color }}
            className={hovered === cp.index && selected ? 'hot' : ''}
            title={`Mile ${Math.round(cp.mile)}: ${cp.risk.label}`}
            onMouseEnter={() => selected && onHover(cp.index)}
            onMouseLeave={() => selected && onHover(null)}
          />
        ))}
      </div>

      <dl className="stats">
        <div><dt>Worst</dt><dd><i className="dot" style={{ background: LEVELS[summary.max_level].color }} />{summary.max_level_label}</dd></div>
        {summary.no_travel_miles > 0 && <div><dt>No Travel</dt><dd>{formatMiles(summary.no_travel_miles)}</dd></div>}
        <div><dt>Severe</dt><dd>{formatMiles(summary.severe_miles)}</dd></div>
        <div><dt>High</dt><dd>{formatMiles(summary.high_miles)}</dd></div>
        <div><dt title="Distance-weighted mean risk level: 0 = all Low, 4 = all No Travel">Avg risk</dt><dd>{summary.average_risk.toFixed(2)}</dd></div>
      </dl>

      {peak && (
        <p className="peak">
          Peak: <strong>{peak.risk.label}</strong> near mile {Math.round(peak.mile)} at {formatTime(peak.eta, peak.timezone)}
          {describeDrivers(peak) && <> — {describeDrivers(peak)}</>}
          {peak.risk.load_rule_applied && ' (raised by load weight)'}
        </p>
      )}
      {route.forecast_missing_checkpoints > 0 && (
        <p className="peak warn">{route.forecast_missing_checkpoints} checkpoint(s) are beyond the forecast range and are not scored.</p>
      )}

      {selected && (
        <div className="checkpoints">
          <div className="checkpoints-head">
            <h4>{route.checkpoints.length} checkpoints</h4>
            <label className={anyRisk ? '' : 'disabled'}>
              <input type="checkbox" checked={riskyOnly && anyRisk} disabled={!anyRisk} onChange={(e) => onRiskyOnlyChange(e.target.checked)} />
              Only Moderate or worse
            </label>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Mile</th><th>ETA (local)</th><th>Wind</th><th>Rain</th><th>Snow</th><th>Risk</th></tr>
              </thead>
              <tbody>
                {rows.map((cp) => (
                  <tr
                    key={cp.index}
                    className={hovered === cp.index ? 'hot' : ''}
                    onMouseEnter={() => onHover(cp.index)}
                    onMouseLeave={() => onHover(null)}
                    onClick={() => onFocus(cp.index)}
                    title="Click to show on the map"
                  >
                    <td>{Math.round(cp.mile)}</td>
                    <td>{formatTime(cp.eta, cp.timezone, 'short')}</td>
                    <td className={cp.risk.wind_level ? `lv${cp.risk.wind_level}` : ''}>{formatNumber(cp.weather?.wind_mph)}</td>
                    <td className={cp.risk.rain_level ? `lv${cp.risk.rain_level}` : ''}>{formatNumber(cp.weather?.rain_in_per_hr, 2)}</td>
                    <td className={cp.risk.snow_level ? `lv${cp.risk.snow_level}` : ''}>{formatNumber(cp.weather?.snow_in_per_hr, 2)}</td>
                    <td><span className="chip" style={{ background: LEVELS[cp.risk.level].color }}>{cp.risk.label}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="units">Wind in mph, rain and snow in inches per hour, forecast for the hour of arrival.</p>
        </div>
      )}
    </article>
  )
}
