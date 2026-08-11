import axios, { AxiosError } from 'axios'
import type {
  ApiErrorBody,
  BillItemCreate,
  BillItemOut,
  BillItemUpdate,
  BillOut,
  BillUpdate,
  DocumentDetail,
  DocumentExtractResponse,
  DocumentSummary,
  DocumentUploadResponse,
  GeneratedFileOut,
  ScenarioConfigRequest,
  ScenarioOut,
  ScenarioPdfResponse,
} from '../types'

const http = axios.create({ baseURL: '/' })

export function apiErrorMessage(err: unknown, fallback = 'Something went wrong.'): string {
  if (axios.isAxiosError(err)) {
    const body = (err as AxiosError<ApiErrorBody>).response?.data
    if (body && typeof body.detail === 'string') return body.detail
  }
  return fallback
}

export const documentsApi = {
  async upload(file: File): Promise<DocumentUploadResponse> {
    const form = new FormData()
    form.append('file', file)
    const { data } = await http.post<DocumentUploadResponse>('/api/documents/upload', form)
    return data
  },
  async extract(documentId: string): Promise<DocumentExtractResponse> {
    const { data } = await http.post<DocumentExtractResponse>(`/api/documents/${documentId}/extract`)
    return data
  },
  async list(): Promise<DocumentSummary[]> {
    const { data } = await http.get<{ documents: DocumentSummary[] }>('/api/documents')
    return data.documents
  },
  async get(documentId: string): Promise<DocumentDetail> {
    const { data } = await http.get<DocumentDetail>(`/api/documents/${documentId}`)
    return data
  },
  async files(documentId: string): Promise<GeneratedFileOut[]> {
    const { data } = await http.get<{ files: GeneratedFileOut[] }>(`/api/documents/${documentId}/files`)
    return data.files
  },
}

export const billsApi = {
  async get(billId: string): Promise<BillOut> {
    const { data } = await http.get<BillOut>(`/api/bills/${billId}`)
    return data
  },
  async update(billId: string, payload: BillUpdate): Promise<BillOut> {
    const { data } = await http.put<BillOut>(`/api/bills/${billId}`, payload)
    return data
  },
  async addItem(billId: string, payload: BillItemCreate): Promise<BillItemOut> {
    const { data } = await http.post<BillItemOut>(`/api/bills/${billId}/items`, payload)
    return data
  },
  async updateItem(billId: string, itemId: string, payload: BillItemUpdate): Promise<BillItemOut> {
    const { data } = await http.put<BillItemOut>(`/api/bills/${billId}/items/${itemId}`, payload)
    return data
  },
  async deleteItem(billId: string, itemId: string): Promise<void> {
    await http.delete(`/api/bills/${billId}/items/${itemId}`)
  },
  async reorderItems(billId: string, itemIdsInOrder: string[]): Promise<BillItemOut[]> {
    const { data } = await http.put<BillItemOut[]>(`/api/bills/${billId}/items/reorder`, {
      item_ids_in_order: itemIdsInOrder,
    })
    return data
  },
  async confirm(billId: string): Promise<{ bill_id: string; confirmed: boolean }> {
    const { data } = await http.post(`/api/bills/${billId}/confirm`)
    return data
  },
  async listScenarios(billId: string): Promise<ScenarioOut[]> {
    const { data } = await http.get<ScenarioOut[]>(`/api/bills/${billId}/scenarios`)
    return data
  },
}

export const scenariosApi = {
  async create(billId: string, payload: ScenarioConfigRequest): Promise<string[]> {
    const { data } = await http.post<{ scenario_ids: string[] }>(`/api/bills/${billId}/scenarios`, payload)
    return data.scenario_ids
  },
  async get(scenarioId: string): Promise<ScenarioOut> {
    const { data } = await http.get<ScenarioOut>(`/api/scenarios/${scenarioId}`)
    return data
  },
  async generatePdf(scenarioId: string): Promise<ScenarioPdfResponse> {
    const { data } = await http.post<ScenarioPdfResponse>(`/api/scenarios/${scenarioId}/pdf`)
    return data
  },
}
