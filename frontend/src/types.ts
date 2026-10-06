export type Role = 'viewer' | 'printer' | 'template_admin'

export interface Me { uid: number; login: string; name: string; role: Role }

export interface FieldVal { raw: unknown; display: string; type: string; uom: string | null }

export interface Row {
  row_id: string
  label: string
  scope: string
  line_id: number | null
  state: string
  fields: Record<string, FieldVal>
  meta: Record<string, unknown>
}

export interface Group {
  id: string
  label: string
  status: 'ok' | 'empty' | 'not_accessible' | 'not_installed' | 'error'
  message: string
  rows: Row[]
}

export interface Resolved { so: string; fetched_at: string; groups: Group[]; warnings: string[] }

export interface CatalogEntry {
  key: string; label: string; group: string; group_label: string; source_path: string
  type: string; scope: string; selectable: boolean; aliases: string[]
}

/** Selection basket: row id -> ticked catalog keys of that row. */
export type Selection = Record<string, string[]>

export interface PresetRule { group: string; keys: string[]; rows: 'all' }
export interface Preset { id: number; name: string; owner_uid: number; shared: boolean; selection: { rules: PresetRule[] } }

export interface Mapping { placeholder: string; catalog_key: string | null; overflow_rule: string; optional: boolean }
export interface TemplateVersion {
  id: number; version: number; created_at: string | null; uploaded_by: number | null; size: string
  orientation: string; scope: string; default_calc_mode: number; original_filename: string
  unresolved: string[]; mappings?: Mapping[]; findings?: string[]; placeholder_kinds?: Record<string, string[]>
}
export interface Template {
  id: number; name: string; description: string; category: string; format: string; size: string
  orientation: string; scope: string; default_calc_mode: number; active: boolean
  active_version_id: number | null; active_version: number | null; latest_version: number | null
  unresolved: string[]; versions?: TemplateVersion[]
}

export interface Warning { code: string; message: string; field?: string; placeholder?: string; label?: string }
export interface CalcOut {
  calculated: Record<string, number | null>; overrides: Record<string, number>
  final: Record<string, number | null>; warnings: Warning[]; mode: number; uom: string
}
export interface LabelSummary { key: string; title: string; calc: CalcOut }
export interface Preview {
  format: 'pdf' | 'zpl'; pdf_base64?: string; text?: string; warnings: Warning[]; render_warnings: string[]
  labels: LabelSummary[]; info: { sheets?: number; slots_per_sheet?: number; empty_slots?: number }
  label_count: number; template: { id: number; name: string; version: number; version_id: number; scope: string }
}

export interface Job {
  id: number; so_name: string; template: string; template_id: number; template_version: number; copies: number
  layout: Record<string, unknown>; printer: string; user_uid: number; format: string; created_at: string | null
  overrides: Record<string, Record<string, unknown>>; calculated: Record<string, CalcOut>
  options: Record<string, unknown>
}

export interface PrintOptions {
  calc_mode: number
  override_base: number
  logo: boolean
  pefc: boolean
  copies: number
  layout: { kind: string; sheet: string; orientation: string; crop_marks: boolean; margin_mm: number; gap_mm: number; start_slot: number }
  printer: string
  /** label key -> {pcs,kgs,cbm} typed by the user (strings, as typed) */
  overrides: Record<string, Record<string, string>>
}
