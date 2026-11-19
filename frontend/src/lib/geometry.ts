export type LngLat = [number, number]

/** Decode an encoded polyline (precision 5) into [lng, lat] pairs for GeoJSON. */
export function decodePolyline(encoded: string): LngLat[] {
  const points: LngLat[] = []
  let index = 0
  let lat = 0
  let lng = 0
  while (index < encoded.length) {
    for (const axis of [0, 1]) {
      let result = 0
      let shift = 0
      let byte: number
      do {
        byte = encoded.charCodeAt(index++) - 63
        result |= (byte & 0x1f) << shift
        shift += 5
      } while (byte >= 0x20)
      const delta = result & 1 ? ~(result >> 1) : result >> 1
      if (axis === 0) lat += delta
      else lng += delta
    }
    points.push([lng / 1e5, lat / 1e5])
  }
  return points
}

const toRad = Math.PI / 180

function haversineMiles(a: LngLat, b: LngLat): number {
  const dLat = (b[1] - a[1]) * toRad
  const dLng = (b[0] - a[0]) * toRad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * toRad) * Math.cos(b[1] * toRad) * Math.sin(dLng / 2) ** 2
  return 2 * 3958.7613 * Math.asin(Math.sqrt(h))
}

/** Running distance at each vertex, scaled so the last value equals `totalMiles`. */
export function cumulativeMiles(coords: LngLat[], totalMiles: number): number[] {
  const cum = [0]
  for (let i = 1; i < coords.length; i++) cum.push(cum[i - 1] + haversineMiles(coords[i - 1], coords[i]))
  const scale = cum[cum.length - 1] ? totalMiles / cum[cum.length - 1] : 1
  return cum.map((m) => m * scale)
}

/** The point `mile` miles along a line. */
export function pointAtMile(coords: LngLat[], cum: number[], mile: number): LngLat {
  if (mile <= 0) return coords[0]
  if (mile >= cum[cum.length - 1]) return coords[coords.length - 1]
  let lo = 0
  let hi = cum.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (cum[mid] <= mile) lo = mid
    else hi = mid
  }
  const t = (mile - cum[lo]) / (cum[hi] - cum[lo] || 1)
  return [coords[lo][0] + (coords[hi][0] - coords[lo][0]) * t, coords[lo][1] + (coords[hi][1] - coords[lo][1]) * t]
}
