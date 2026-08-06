export type Position = [number, number, ...number[]]
export type Coordinates = Position | Coordinates[]

export type Feature = {
  id?: string | number
  type: 'Feature'
  geometry: {
    type: string
    coordinates?: Coordinates
  } | null
  properties?: Record<string, unknown> | null
}

export type FeatureCollection = {
  type: 'FeatureCollection'
  features: Feature[]
}
