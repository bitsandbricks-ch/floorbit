export interface Hall {
  id: string
  name: string
  background: string | null
  /** Where the background sits (drawing units on the plan, % on a hall) and how see-through it is. */
  background_frame?: { x: number; y: number; w: number; h: number } | null
  background_opacity?: number | null
  /** Metres per seat (one grid cell), from calibrating; null when not known. */
  seat_m?: number | null
  switches: number
  seat_blocks: number
}

export interface TemplateVersion {
  n: number
  saved: string
  halls: number
  switches: number
  seat_blocks: number
}

export interface LayoutTemplate {
  id: string
  name: string
  description: string
  created: string
  updated: string
  versions: TemplateVersion[]
  dropped?: string[]
}

export interface ApplyResult {
  halls: number
  seat_blocks: number
  switches_placed: number
  switches_added: number
}
