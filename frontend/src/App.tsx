import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import HeatmapControl from './components/HeatmapControl'
import MapView, { type Focus } from './components/MapView'
import RouteCard from './components/RouteCard'
import TripForm from './components/TripForm'
import { fetchHeatmap, planTrip } from './lib/api'
import { formatTime } from './lib/format'
import { LEVELS, RULES } from './lib/risk'
import type { Heatmap, Metric, Plan, TripRequest } from './lib/types'

const PLAY_HOURS_PER_SECOND = 4

export default function App() {
  const [interval, setIntervalMiles] = useState(25)
  const [trip, setTrip] = useState<TripRequest | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [planning, setPlanning] = useState(false)
  const [planError, setPlanError] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hovered, setHovered] = useState<number | null>(null)
  const [focus, setFocus] = useState<Focus | null>(null)
  const [riskyOnly, setRiskyOnly] = useState(false)

  const [heatmap, setHeatmap] = useState<Heatmap | null>(null)
  const [heatLoading, setHeatLoading] = useState(false)
  const [heatError, setHeatError] = useState('')
  const [heatVisible, setHeatVisible] = useState(true)
  const [metric, setMetric] = useState<Metric>('risk')
  const [hour, setHour] = useState(0)
  const [playing, setPlaying] = useState(false)

  const planRequest = useRef<AbortController | null>(null)
  const heatRequest = useRef<AbortController | null>(null)

  const run = useCallback((next: TripRequest, keepSelection: boolean) => {
    planRequest.current?.abort()
    heatRequest.current?.abort()
    const controller = new AbortController()
    planRequest.current = controller
    setTrip(next)
    setPlanning(true)
    setPlanError('')
    setHovered(null)

    planTrip(next, controller.signal)
      .then((result) => {
        setPlan(result)
        setSelectedId((current) =>
          keepSelection && current && result.routes.some((r) => r.id === current) ? current : result.recommendation.route_id,
        )
        setPlanning(false)

        // The heatmap only depends on the places, time and load, so a change
        // of sampling interval does not need to reload it.
        if (keepSelection) return
        const heatController = new AbortController()
        heatRequest.current = heatController
        setHeatmap(null)
        setHeatError('')
        setHeatLoading(true)
        setPlaying(false)
        setHour(0)
        fetchHeatmap(next, heatController.signal)
          .then(setHeatmap)
          .catch((error: Error) => error.name !== 'AbortError' && setHeatError(error.message))
          .finally(() => !heatController.signal.aborted && setHeatLoading(false))
      })
      .catch((error: Error) => {
        if (error.name === 'AbortError') return
        setPlanError(error.message)
        setPlanning(false)
      })
  }, [])

  const changeInterval = (miles: number) => {
    setIntervalMiles(miles)
    if (trip && plan) run({ ...trip, interval_miles: miles }, true)
  }

  // Forecast animation: advance the slider smoothly and loop at the end.
  useEffect(() => {
    if (!playing || !heatmap) return
    let frame = 0
    let last = performance.now()
    const tick = (now: number) => {
      const elapsed = (now - last) / 1000
      last = now
      setHour((h) => (h + elapsed * PLAY_HOURS_PER_SECOND) % heatmap.hours)
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, heatmap])

  const selectRoute = useCallback((id: string) => {
    setSelectedId(id)
    setHovered(null)
  }, [])

  const recommended = plan?.routes.find((r) => r.recommended)
  // Times are shown in the local time of the place they refer to.
  const originZone = plan?.routes[0]?.checkpoints[0]?.timezone
  const fewer = plan && plan.meta.route_count < plan.meta.requested_route_count

  // The panel is memoised so that the forecast animation (which updates
  // `hour` every frame) re-renders only the map and the slider.
  const sidebar = useMemo(
    () => (
      <aside className="sidebar">
        <header className="brand">
          <span className="logo" aria-hidden>
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 17V7h10v10M13 10h4l4 4v3h-8" /><circle cx="7.5" cy="17.5" r="1.8" /><circle cx="17.5" cy="17.5" r="1.8" />
            </svg>
          </span>
          <div>
            <h1>Weather-Aware Truck Routing</h1>
            <p>Compare three routes by forecast wind, rain and snow at the time you would be there.</p>
          </div>
        </header>

        <TripForm busy={planning} interval={interval} onIntervalChange={changeInterval} onSubmit={(next) => run(next, false)} />

        <div className="results" aria-live="polite">
          {planError && (
            <div className="alert error" role="alert">
              <strong>Could not plan this trip.</strong> {planError}
            </div>
          )}

          {planning && !plan && (
            <div className="skeletons" aria-label="Planning routes">
              <p className="status"><span className="spinner small" aria-hidden /> Finding routes and sampling the forecast…</p>
              <div className="skeleton" /><div className="skeleton" /><div className="skeleton" />
            </div>
          )}

          {plan && recommended && (
            <div className={`stack${planning ? ' stale' : ''}`}>
              <div className={`alert ${plan.recommendation.no_safe_route ? 'danger' : 'good'}`}>
                {plan.recommendation.no_safe_route ? (
                  <>
                    <strong>No safe option at this departure time.</strong> Every route crosses No Travel conditions. Route {recommended.id} is the least exposed; consider leaving at a different time.
                  </>
                ) : (
                  <>
                    <strong>Take Route {recommended.id}{recommended.name ? ` via ${recommended.name}` : ''}.</strong> {plan.recommendation.reason}
                  </>
                )}
              </div>

              <p className="context">
                Leaving {formatTime(plan.request.departure_time, originZone)} · {plan.request.load_weight_lb.toLocaleString()} lb · weather every {plan.request.interval_miles} mi
              </p>
              {fewer && (
                <p className="context warn">Only {plan.meta.route_count} distinct route{plan.meta.route_count === 1 ? ' exists' : 's exist'} between these places.</p>
              )}

              {plan.routes.map((route) => (
                <RouteCard
                  key={route.id}
                  route={route}
                  selected={route.id === selectedId}
                  onSelect={() => selectRoute(route.id)}
                  hovered={route.id === selectedId ? hovered : null}
                  onHover={setHovered}
                  onFocus={(index) => {
                    setHovered(index)
                    setFocus({ routeId: route.id, index, nonce: Date.now() })
                  }}
                  riskyOnly={riskyOnly}
                  onRiskyOnlyChange={setRiskyOnly}
                />
              ))}
            </div>
          )}

          {!plan && !planning && !planError && (
            <p className="empty">Enter a trip to see three route options ranked by weather risk and travel time.</p>
          )}

          <details className="rules">
            <summary>How risk is scored</summary>
            <table>
              <thead>
                <tr>
                  <th>Condition</th>
                  {LEVELS.map((level) => (
                    <th key={level.key}><i className="dot" style={{ background: level.color }} />{level.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {RULES.map((rule) => (
                  <tr key={rule.condition}>
                    <th>{rule.condition}</th>
                    {rule.bands.map((band) => <td key={band}>{band}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
            <ul>
              <li>A checkpoint takes the worst of its wind, rain and snow levels.</li>
              <li>Wind 45–54 mph with a load over 30,000 lb is No Travel.</li>
              <li>Wind 35–44 mph with a load over 40,000 lb is Severe.</li>
              <li>Routes are ranked by fewest Severe miles, then fewest High miles, then lowest average risk, then shortest travel time. No Travel miles count before all of these.</li>
            </ul>
          </details>
        </div>
      </aside>
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [interval, trip, plan, planning, planError, selectedId, hovered, riskyOnly],
  )

  return (
    <div className="app">
      {sidebar}
      <main className="stage">
        <MapView
          plan={plan}
          selectedId={selectedId}
          onSelect={selectRoute}
          heatmap={heatmap}
          heatVisible={heatVisible}
          metric={metric}
          hour={hour}
          hovered={hovered}
          onHover={setHovered}
          focus={focus}
        />
        <div className="legend" aria-label="Risk levels">
          {LEVELS.map((level) => (
            <span key={level.key}><i className="dot" style={{ background: level.color }} />{level.label}</span>
          ))}
        </div>
        {planning && <div className="map-status"><span className="spinner small" aria-hidden /> Planning routes…</div>}
        <HeatmapControl
          heatmap={heatmap}
          timeZone={originZone}
          loading={heatLoading}
          error={heatError}
          visible={heatVisible}
          onVisibleChange={(visible) => {
            setHeatVisible(visible)
            if (!visible) setPlaying(false)
          }}
          metric={metric}
          onMetricChange={setMetric}
          hour={hour}
          onHourChange={setHour}
          playing={playing}
          onPlayingChange={setPlaying}
        />
      </main>
    </div>
  )
}
