import type { LevelKey, Metric } from './types'

export interface Level {
  key: LevelKey
  label: string
  color: string
}

// Index = numeric risk level returned by the API (0 = Low ... 4 = No Travel).
export const LEVELS: Level[] = [
  { key: 'low', label: 'Low', color: '#2f9e63' },
  { key: 'moderate', label: 'Moderate', color: '#e0b400' },
  { key: 'high', label: 'High', color: '#f0812b' },
  { key: 'severe', label: 'Severe', color: '#d92d3a' },
  { key: 'no_travel', label: 'No Travel', color: '#6b21a8' },
]

export const levelColor = (level: number) => LEVELS[Math.max(0, Math.min(4, level))].color

export interface MetricScale {
  label: string
  unit: string
  /** value -> [colour, opacity] stops, ascending, used by the map and legend. */
  stops: [number, string, number][]
  ticks: { value: number; label: string }[]
}

// The stops at each threshold use the same colours as the risk levels, so a
// yellow patch always means "Moderate for this condition", and so on.
export const METRICS: Record<Metric, MetricScale> = {
  risk: {
    label: 'Risk',
    unit: '',
    stops: [
      [0, LEVELS[0].color, 0.14],
      [1, LEVELS[1].color, 0.44],
      [2, LEVELS[2].color, 0.54],
      [3, LEVELS[3].color, 0.62],
      [4, LEVELS[4].color, 0.7],
    ],
    ticks: LEVELS.map((l, i) => ({ value: i, label: l.label })),
  },
  wind: {
    label: 'Wind',
    unit: 'mph',
    stops: [
      [0, '#5aa9e6', 0.0],
      [8, '#5aa9e6', 0.12],
      [18, LEVELS[0].color, 0.26],
      [25, LEVELS[1].color, 0.44],
      [35, LEVELS[2].color, 0.54],
      [45, LEVELS[3].color, 0.62],
      [55, LEVELS[4].color, 0.7],
    ],
    ticks: [0, 25, 35, 45, 55].map((v) => ({ value: v, label: String(v) })),
  },
  rain: {
    label: 'Rain',
    unit: 'in/hr',
    stops: [
      [0, '#5aa9e6', 0.0],
      [0.01, '#5aa9e6', 0.22],
      [0.05, '#2f7fd1', 0.36],
      [0.1, LEVELS[1].color, 0.46],
      [0.25, LEVELS[2].color, 0.54],
      [0.5, LEVELS[3].color, 0.62],
      [1.0, LEVELS[4].color, 0.7],
    ],
    ticks: [0, 0.1, 0.25, 0.5, 1].map((v) => ({ value: v, label: String(v) })),
  },
  snow: {
    label: 'Snow',
    unit: 'in/hr',
    stops: [
      [0, '#9fb4f5', 0.0],
      [0.02, '#9fb4f5', 0.24],
      [0.25, '#6f86ea', 0.38],
      [0.5, LEVELS[1].color, 0.46],
      [1.0, LEVELS[2].color, 0.54],
      [2.0, LEVELS[3].color, 0.62],
      [3.0, LEVELS[4].color, 0.7],
    ],
    ticks: [0, 0.5, 1, 2, 3].map((v) => ({ value: v, label: String(v) })),
  },
}

/** The thresholds from the brief, shown in the "How risk is scored" panel. */
export const RULES = [
  { condition: 'Wind (mph)', bands: ['< 25', '25–34', '35–44', '45–54', '≥ 55'] },
  { condition: 'Rain (in/hr)', bands: ['< 0.10', '0.10–0.25', '0.25–0.50', '0.50–1.00', '> 1.00'] },
  { condition: 'Snow (in/hr)', bands: ['< 0.5', '0.5–1.0', '1.0–2.0', '2.0–3.0', '> 3.0'] },
]
