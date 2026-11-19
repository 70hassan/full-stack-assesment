import maplibregl, { type ExpressionSpecification, type GeoJSONSource, type StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { describeWeather, formatNumber, formatTime } from '../lib/format'
import { cumulativeMiles, decodePolyline, pointAtMile, type LngLat } from '../lib/geometry'
import { LEVELS, METRICS } from '../lib/risk'
import type { Checkpoint, Heatmap, Metric, Plan, RouteOption } from '../lib/types'

const VECTOR_STYLE = 'https://tiles.openfreemap.org/styles/positron'
// Used only if the vector style cannot be loaded.
const RASTER_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '&copy; OpenStreetMap contributors',
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
}

const US_BOUNDS: [[number, number], [number, number]] = [[-124.8, 24.5], [-66.9, 49.4]]
const EMPTY: import('geojson').FeatureCollection = { type: 'FeatureCollection', features: [] }
const LEVEL_COLOR: ExpressionSpecification = [
  'match', ['get', 'level'],
  0, LEVELS[0].color, 1, LEVELS[1].color, 2, LEVELS[2].color, 3, LEVELS[3].color, 4, LEVELS[4].color,
  '#64748b',
]

export interface Focus {
  routeId: string
  index: number
  nonce: number
}

interface Props {
  plan: Plan | null
  selectedId: string | null
  onSelect: (id: string) => void
  heatmap: Heatmap | null
  heatVisible: boolean
  metric: Metric
  hour: number
  hovered: number | null
  onHover: (index: number | null) => void
  focus: Focus | null
}

interface Shape {
  coords: LngLat[]
  cum: number[]
}

function el(tag: string, className: string, text?: string): HTMLElement {
  const node = document.createElement(tag)
  node.className = className
  if (text != null) node.textContent = text
  return node
}

function checkpointPopup(cp: Checkpoint): HTMLElement {
  const root = el('div', 'popup')
  const head = el('div', 'popup-head')
  const chip = el('span', 'chip', cp.risk.label)
  chip.style.background = LEVELS[cp.risk.level].color
  head.append(chip, el('strong', '', `Mile ${Math.round(cp.mile)}`))
  root.append(head, el('div', 'popup-eta', `ETA ${formatTime(cp.eta, cp.timezone)}`))
  if (!cp.weather) {
    root.append(el('div', 'popup-note', 'No forecast is available for this time.'))
    return root
  }
  const w = cp.weather
  const grid = el('dl', 'popup-grid')
  const rows: [string, string, number][] = [
    ['Wind', `${formatNumber(w.wind_mph)} mph${w.gust_mph != null ? ` (gusts ${formatNumber(w.gust_mph)})` : ''}`, cp.risk.wind_level],
    ['Rain', `${formatNumber(w.rain_in_per_hr, 2)} in/hr`, cp.risk.rain_level],
    ['Snow', `${formatNumber(w.snow_in_per_hr, 2)} in/hr`, cp.risk.snow_level],
  ]
  for (const [name, value, level] of rows) {
    const dt = el('dt', '', name)
    const dd = el('dd', '', value)
    if (level > 0) {
      const dot = el('i', 'dot')
      dot.style.background = LEVELS[level].color
      dot.title = LEVELS[level].label
      dd.prepend(dot)
    }
    grid.append(dt, dd)
  }
  root.append(grid)
  const sky = [describeWeather(w.weather_code), w.temperature_f != null ? `${Math.round(w.temperature_f)}°F` : '']
    .filter(Boolean)
    .join(' · ')
  if (sky) root.append(el('div', 'popup-note', sky))
  if (cp.risk.load_rule_applied) root.append(el('div', 'popup-note warn', 'Raised one level by the load-weight rule.'))
  return root
}

/** Where the truck is `elapsedSeconds` after departure, from the checkpoint ETAs. */
function truckPosition(route: RouteOption, shape: Shape, departure: number, elapsedSeconds: number): LngLat | null {
  if (elapsedSeconds < 0 || elapsedSeconds > route.duration_seconds) return null
  const t = departure + elapsedSeconds * 1000
  const cps = route.checkpoints
  let i = 1
  while (i < cps.length - 1 && new Date(cps[i].eta).getTime() < t) i++
  const t0 = new Date(cps[i - 1].eta).getTime()
  const t1 = new Date(cps[i].eta).getTime()
  const f = t1 > t0 ? Math.min(1, Math.max(0, (t - t0) / (t1 - t0))) : 0
  return pointAtMile(shape.coords, shape.cum, cps[i - 1].mile + (cps[i].mile - cps[i - 1].mile) * f)
}

export default function MapView(props: Props) {
  const { plan, selectedId, onSelect, heatmap, heatVisible, metric, hour, hovered, onHover, focus } = props
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markers = useRef<maplibregl.Marker[]>([])
  const truck = useRef<maplibregl.Marker | null>(null)
  const popup = useRef<maplibregl.Popup | null>(null)
  const callbacks = useRef({ onSelect, onHover })
  callbacks.current = { onSelect, onHover }
  const selectedRef = useRef<RouteOption | null>(null)
  const [ready, setReady] = useState(false)

  const shapes = useMemo(() => {
    const out = new Map<string, Shape>()
    for (const route of plan?.routes ?? []) {
      const coords = decodePolyline(route.geometry)
      out.set(route.id, { coords, cum: cumulativeMiles(coords, route.distance_miles) })
    }
    return out
  }, [plan])
  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null
  selectedRef.current = selected

  // --- create the map once -------------------------------------------------
  useEffect(() => {
    const map = new maplibregl.Map({
      container: container.current!,
      style: VECTOR_STYLE,
      // Start on the contiguous United States, whatever the window size.
      bounds: US_BOUNDS,
      fitBoundsOptions: { padding: { top: 60, bottom: 150, left: 30, right: 30 } },
      minZoom: 2,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.dragRotate.disable()
    map.touchZoomRotate.disableRotation()

    let fellBack = false
    const ready_ref = { current: false }
    map.on('error', (event) => {
      if (!fellBack && !ready_ref.current) {
        const message = String((event as { error?: Error }).error?.message ?? '')
        if (/style|Failed to fetch|NetworkError/i.test(message)) {
          fellBack = true
          map.setStyle(RASTER_STYLE)
        }
      }
    })

    const setup = () => {
      if (map.getSource('routes')) return
      const labels = map.getStyle().layers?.find((layer) => layer.type === 'symbol')?.id
      for (const id of ['heat', 'routes', 'segments', 'checkpoints']) {
        map.addSource(id, { type: 'geojson', data: EMPTY })
      }
      map.addLayer({ id: 'heat', type: 'circle', source: 'heat', paint: { 'circle-blur': 1, 'circle-opacity': 0 } }, labels)
      const round = { 'line-cap': 'round', 'line-join': 'round' } as const
      map.addLayer({
        id: 'routes-casing', type: 'line', source: 'routes', layout: round,
        paint: { 'line-color': '#ffffff', 'line-width': ['case', ['get', 'selected'], 10, 7], 'line-opacity': 0.95 },
      }, labels)
      map.addLayer({
        id: 'routes-line', type: 'line', source: 'routes', layout: round,
        filter: ['!', ['get', 'selected']],
        paint: { 'line-color': '#64748b', 'line-width': 4, 'line-opacity': 0.8 },
      }, labels)
      map.addLayer({
        id: 'segments', type: 'line', source: 'segments', layout: round,
        paint: { 'line-color': LEVEL_COLOR, 'line-width': 6 },
      }, labels)
      // A wide invisible line makes the unselected routes easy to click.
      map.addLayer({
        id: 'routes-hit', type: 'line', source: 'routes',
        paint: { 'line-color': '#000', 'line-opacity': 0, 'line-width': 22 },
      })
      map.addLayer({
        id: 'checkpoints', type: 'circle', source: 'checkpoints',
        paint: {
          'circle-color': LEVEL_COLOR,
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 2.5, 6, 4.5, 10, 7],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 3, 0.8, 8, 2],
        },
      })
      map.addLayer({
        id: 'checkpoint-active', type: 'circle', source: 'checkpoints',
        filter: ['==', ['get', 'index'], -1],
        paint: {
          'circle-color': LEVEL_COLOR, 'circle-radius': 10,
          'circle-stroke-color': '#0f172a', 'circle-stroke-width': 3,
        },
      })

      map.on('click', 'routes-hit', (event) => {
        const id = event.features?.[0]?.properties?.id
        if (id) callbacks.current.onSelect(id)
      })
      map.on('mouseenter', 'routes-hit', () => (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', 'routes-hit', () => (map.getCanvas().style.cursor = ''))
      map.on('mousemove', 'checkpoints', (event) => {
        const index = event.features?.[0]?.properties?.index
        if (typeof index === 'number') callbacks.current.onHover(index)
      })
      map.on('mouseleave', 'checkpoints', () => callbacks.current.onHover(null))
      ready_ref.current = true
      setReady(true)
    }
    map.on('load', setup)
    map.on('styledata', () => map.isStyleLoaded() && setup())

    const observer = new ResizeObserver(() => map.resize())
    observer.observe(container.current!)
    return () => {
      observer.disconnect()
      map.remove()
      mapRef.current = null
    }
  }, [])

  // --- routes, markers and camera: when a new plan arrives ------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    markers.current.forEach((m) => m.remove())
    markers.current = []
    if (!plan) return

    const bounds = new maplibregl.LngLatBounds()
    for (const route of plan.routes) {
      const shape = shapes.get(route.id)!
      shape.coords.forEach((c) => bounds.extend(c))
      const badge = el('button', `route-badge${route.recommended ? ' recommended' : ''}`, route.id)
      badge.title = `Route ${route.id}${route.recommended ? ' (recommended)' : ''}`
      badge.addEventListener('click', () => callbacks.current.onSelect(route.id))
      markers.current.push(
        new maplibregl.Marker({ element: badge }).setLngLat(pointAtMile(shape.coords, shape.cum, route.distance_miles / 2)).addTo(map),
      )
    }
    const { origin, destination } = plan.request
    markers.current.push(
      new maplibregl.Marker({ element: el('div', 'pin pin-origin', 'Start'), anchor: 'bottom', offset: [0, -7] }).setLngLat([origin.lon, origin.lat]).addTo(map),
      new maplibregl.Marker({ element: el('div', 'pin pin-destination', 'End'), anchor: 'bottom', offset: [0, -7] }).setLngLat([destination.lon, destination.lat]).addTo(map),
    )
    map.fitBounds(bounds, { padding: { top: 70, bottom: 190, left: 60, right: 60 }, duration: 700, maxZoom: 11 })
  }, [plan, shapes, ready])

  // --- selection: line styling, risk-coloured segments and checkpoints ------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const source = (id: string) => map.getSource(id) as GeoJSONSource
    source('routes').setData({
      type: 'FeatureCollection',
      features: (plan?.routes ?? []).map((route) => ({
        type: 'Feature',
        properties: { id: route.id, selected: route.id === selectedId },
        geometry: { type: 'LineString', coordinates: shapes.get(route.id)!.coords },
      })),
    })
    const shape = selected && shapes.get(selected.id)
    source('segments').setData({
      type: 'FeatureCollection',
      features: !selected || !shape ? [] : selected.checkpoints
        .filter((cp) => cp.span.to_index > cp.span.from_index)
        .map((cp) => ({
          type: 'Feature',
          properties: { level: cp.risk.level },
          geometry: { type: 'LineString', coordinates: shape.coords.slice(cp.span.from_index, cp.span.to_index + 1) },
        })),
    })
    source('checkpoints').setData({
      type: 'FeatureCollection',
      features: (selected?.checkpoints ?? []).map((cp) => ({
        type: 'Feature',
        properties: { index: cp.index, level: cp.risk.level },
        geometry: { type: 'Point', coordinates: [cp.lon, cp.lat] },
      })),
    })
    document.querySelectorAll('.route-badge').forEach((node) => {
      node.classList.toggle('selected', node.textContent === selectedId)
    })
  }, [plan, shapes, selected, selectedId, ready])

  // --- hovered checkpoint: ring + popup ------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    map.setFilter('checkpoint-active', ['==', ['get', 'index'], hovered ?? -1])
    popup.current?.remove()
    popup.current = null
    const cp = hovered != null ? selectedRef.current?.checkpoints[hovered] : null
    if (cp) {
      popup.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 14, maxWidth: '260px' })
        .setLngLat([cp.lon, cp.lat])
        .setDOMContent(checkpointPopup(cp))
        .addTo(map)
    }
  }, [hovered, selectedId, ready])

  // --- "show on map" from the checkpoint list -------------------------------
  useEffect(() => {
    const map = mapRef.current
    const cp = focus && selectedRef.current?.id === focus.routeId ? selectedRef.current.checkpoints[focus.index] : null
    if (map && ready && cp) map.easeTo({ center: [cp.lon, cp.lat], zoom: Math.max(map.getZoom(), 8), duration: 600 })
  }, [focus, ready])

  // --- heatmap data: one feature per corridor cell, one property per hour ---
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const source = map.getSource('heat') as GeoJSONSource
    if (!heatmap) {
      source.setData(EMPTY)
      return
    }
    source.setData({
      type: 'FeatureCollection',
      features: heatmap.points.map((point) => ({
        type: 'Feature',
        properties: Object.fromEntries(point[metric].map((value, h) => [`h${h}`, value])),
        geometry: { type: 'Point', coordinates: [point.lon, point.lat] },
      })),
    })
    // Circle radius in pixels that keeps pace with the map scale, so each
    // blurred circle always covers its own grid cell and blends into the next.
    const pixelsPerDegreeAtZoom0 = 512 / 360
    const radius = heatmap.cell_degrees * pixelsPerDegreeAtZoom0 * 1.25
    map.setPaintProperty('heat', 'circle-radius', ['interpolate', ['exponential', 2], ['zoom'], 0, radius, 22, radius * 2 ** 22])
  }, [heatmap, metric, ready])

  // --- heatmap time: only paint expressions change, so scrubbing is instant -
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    if (!heatmap || !heatVisible) {
      map.setPaintProperty('heat', 'circle-opacity', 0)
      return
    }
    const clamped = Math.max(0, Math.min(heatmap.hours, hour))
    const i = Math.min(heatmap.hours - 1, Math.floor(clamped))
    const t = clamped - i
    const value = (t === 0
      ? ['to-number', ['get', `h${i}`], 0]
      : ['+', ['*', ['to-number', ['get', `h${i}`], 0], 1 - t], ['*', ['to-number', ['get', `h${i + 1}`], 0], t]]) as ExpressionSpecification
    const stops = METRICS[metric].stops
    map.setPaintProperty('heat', 'circle-color', ['interpolate', ['linear'], value, ...stops.flatMap(([v, c]) => [v, c])] as unknown as ExpressionSpecification)
    map.setPaintProperty('heat', 'circle-opacity', ['interpolate', ['linear'], value, ...stops.flatMap(([v, , o]) => [v, o])] as unknown as ExpressionSpecification)
  }, [heatmap, heatVisible, metric, hour, ready])

  // --- truck marker: where the selected route's truck is at the slider time -
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const shape = selected && shapes.get(selected.id)
    let position: LngLat | null = null
    if (plan && selected && shape && heatmap && heatVisible) {
      const departure = new Date(plan.request.departure_time).getTime()
      const moment = new Date(heatmap.start_time).getTime() + hour * 3600_000
      position = truckPosition(selected, shape, departure, Math.max(0, (moment - departure) / 1000))
    }
    if (!position) {
      truck.current?.remove()
      truck.current = null
      return
    }
    if (!truck.current) {
      const node = el('div', 'truck')
      node.title = 'Estimated truck position at the selected time'
      truck.current = new maplibregl.Marker({ element: node }).setLngLat(position).addTo(map)
    } else {
      truck.current.setLngLat(position)
    }
  }, [plan, selected, shapes, heatmap, heatVisible, hour, ready])

  return <div ref={container} className="map" aria-label="Map of route options" />
}
