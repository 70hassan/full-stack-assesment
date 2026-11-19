export type LevelKey = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'
export type Metric = 'risk' | 'wind' | 'rain' | 'snow'

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface Weather {
  wind_mph: number
  gust_mph: number | null
  rain_in_per_hr: number | null
  snow_in_per_hr: number | null
  temperature_f: number | null
  weather_code: number | null
}

export interface Checkpoint {
  index: number
  mile: number
  lat: number
  lon: number
  eta: string
  utc_offset_seconds: number
  timezone: string
  weather: Weather | null
  risk: {
    level: number
    key: LevelKey
    label: string
    wind_level: number
    rain_level: number
    snow_level: number
    drivers: ('wind' | 'rain' | 'snow')[]
    load_rule_applied: boolean
  }
  span: { from_mile: number; to_mile: number; from_index: number; to_index: number }
}

export interface RouteSummary {
  miles_by_level: Record<LevelKey, number>
  no_travel_miles: number
  severe_miles: number
  high_miles: number
  average_risk: number
  max_level: number
  max_level_key: LevelKey
  max_level_label: string
  duration_seconds: number
}

export interface RouteOption {
  id: string
  rank: number
  recommended: boolean
  name: string
  distance_miles: number
  duration_seconds: number
  arrival_time: string
  arrival_timezone: string
  summary: RouteSummary
  forecast_missing_checkpoints: number
  geometry: string
  checkpoints: Checkpoint[]
}

export interface Plan {
  request: {
    origin: Place
    destination: Place
    departure_time: string
    load_weight_lb: number
    interval_miles: number
  }
  routes: RouteOption[]
  recommendation: {
    route_id: string
    criterion: string | null
    reason: string
    no_safe_route: boolean
  }
  meta: {
    route_count: number
    requested_route_count: number
    weather_lookups: number
    weather_cell_degrees: number
    processing_ms: number
  }
}

export interface HeatPoint {
  lat: number
  lon: number
  wind: number[]
  rain: number[]
  snow: number[]
  risk: number[]
}

export interface Heatmap {
  start_time: string
  hours: number
  cell_degrees: number
  points: HeatPoint[]
}

export interface TripRequest {
  origin: Place
  destination: Place
  departure_time: string
  load_weight_lb: number
  interval_miles: number
}
