export type Role = 'viewer' | 'printer' | 'template_admin'

export interface Me { uid: number; login: string; name: string; role: Role }

export interface FieldVal { label: string; raw: unknown; display: string; type: string; uom: string | null }

/** A saved label PDF as offered for an order line. `id` is its saved record; the file is fetched by its saved location. */
export interface LabelFile { id: number; name: string; folder: string; location_id: number }

/** The label PDFs found for one order line's item code. */
/** A request for a missing label file (open until a file for that item code shows up in the Label files list). */
export interface LineRequest { id: number; created_at: string | null; requested_by_name: string }

/** An open label request for an item code. It is done when the code has `expected` label files (it has `files_now`). */
export interface LineReq {
  id: number; kind: 'missing' | 'change'; note: string; created_at: string | null; requested_by_name: string
  expected: number; files_now: number
}

export interface LinePdf {
  code: string; files: LabelFile[]; selected: number | null; request: LineRequest | null
  file_count: number; requests: LineReq[]
}

export interface Row {
  row_id: string
  label: string
  line_id: number | null
  state: string
  fields: Record<string, FieldVal>
  /** greyed (ordered qty 0) or warning colour (no usable label PDF); either way it cannot be ticked or printed */
  disabled: boolean
  disabled_reason: string
  disabled_kind: '' | 'no_qty' | 'no_label'
  pdf?: LinePdf
  /** reference rows only: the order lines whose product this transfer moves */
  line_ids?: number[]
}

export interface Group {
  id: string
  label: string
  status: 'ok' | 'empty' | 'not_accessible' | 'not_installed' | 'error'
  message: string
  rows: Row[]
}

export interface Resolved { so: string; fetched_at: string; groups: Group[] }

export interface PrintItem { line_id: number; file_id: number | null }

export interface JobItem { line_id: number; code: string; name: string; file_id: number; path: string; sha256: string | null; size: number }
export interface Job {
  id: number; so_name: string; user_uid: number; copies: number; printer: string; reprint_of: number | null
  created_at: string | null; items: JobItem[]
}

/** A folder that was added by URL. */
export interface LocationInfo {
  id: number; url: string; folder: string; reachable: boolean; files: number; missing: number
  last_fetched_at: string | null; last_checked_at: string | null
}
export interface LabelStatus { locations: LocationInfo[]; files: number; missing: number; codes: number }

/** One saved file in the Label files list. status "missing" = renamed, moved or deleted since it was saved. */
export interface LabelRow {
  id: number; name: string; folder: string; url: string | null; location_id: number; location: string
  status: 'ok' | 'missing'; size: number; last_checked: string | null
}
export interface LabelSearch { total: number; page: number; size: number; items: LabelRow[] }

export interface LabelRequestRow {
  id: number; code: string; name: string; so: string; status: 'open' | 'solved'; kind: 'missing' | 'change'; note: string
  expected: number; files_now?: number
  requested_by: number; requested_by_name: string; created_at: string | null; solved_at: string | null
  file_id: number | null; file_name: string | null; file_url: string | null
}
export interface LabelRequests { items: LabelRequestRow[]; counts: { open: number; solved: number } }
