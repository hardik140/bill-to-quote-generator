// Mirrors backend/app/schemas/*.py. Money fields arrive as numbers
// (Pydantic Decimal -> JSON) and are formatted for display only;
// all real arithmetic happens server-side with Decimal (TRD FR-06).

export interface DocumentUploadResponse {
  document_id: string
  status: string
}

export interface DocumentExtractResponse {
  document_id: string
  status: string
  bill_id: string
}

export interface DocumentSummary {
  id: string
  original_filename: string
  uploaded_at: string
  status: string
  grand_total: number | null
  scenario_count: number
}

export interface DocumentDetail {
  id: string
  original_filename: string
  mime_type: string
  file_size: number
  uploaded_at: string
  status: string
  bill_id: string | null
  preview_url: string
}

export interface GeneratedFileOut {
  id: string
  scenario_id: string
  file_type: string
  filename: string
  storage_path: string
  generated_at: string
}

export interface BillItemOut {
  id: string
  serial_no: number
  description: string
  rate: number
  confidence: number | null
  user_verified: boolean
  low_confidence: boolean
}

export interface BillOut {
  id: string
  document_id: string
  currency: string
  subtotal: number
  tax_total: number
  grand_total: number
  extraction_status: string
  confirmed: boolean
  created_at: string
  updated_at: string
  items: BillItemOut[]
}

export interface BillItemUpdate {
  description?: string
  rate?: number
}

export interface BillItemCreate {
  description: string
  rate: number
}

export type RoundingMode = 'none' | 'nearest_1' | 'nearest_5' | 'nearest_10'

export interface ScenarioConfigRequest {
  scenario_b_markup_percent: number
  scenario_c_markup_percent: number
  rounding: RoundingMode
}

export interface ScenarioItemOut {
  id: string
  source_item_id: string
  description: string
  quantity: number
  unit: string | null
  baseline_rate: number
  markup_percent: number
  adjusted_rate: number
  line_amount: number
  tax_amount: number
  total_amount: number
}

export interface ScenarioOut {
  id: string
  bill_id: string
  scenario_type: 'BASELINE' | 'SIMULATED'
  label: string
  markup_percent: number
  rounding_mode: string
  subtotal: number
  tax_total: number
  grand_total: number
  disclaimer: string | null
  created_at: string
  items: ScenarioItemOut[]
}

export interface ScenarioPdfResponse {
  scenario_id: string
  filename: string
  storage_path: string
  file_hash: string
}

export interface ApiErrorBody {
  detail: string
}
