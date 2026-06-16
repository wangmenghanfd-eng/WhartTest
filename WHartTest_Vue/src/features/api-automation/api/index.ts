import request from '@/utils/request'
import type {
  ApiBatchExecutionRecord,
  ApiDefinition,
  ApiEnvironmentConfig,
  ApiExecutionRecord,
  ApiModule,
  ApiPublicData,
  ApiScript,
  ApiTestCase,
  PaginatedResponse,
} from '../types'

const BASE_URL = '/api-automation'

export const apiModuleApi = {
  list: (params?: { project?: number; parent?: number | null; search?: string }) =>
    request.get<PaginatedResponse<ApiModule>>(`${BASE_URL}/modules/`, { params }),
  tree: (project: number) => request.get<ApiModule[]>(`${BASE_URL}/modules/tree/`, { params: { project } }),
  create: (data: Partial<ApiModule>) => request.post<ApiModule>(`${BASE_URL}/modules/`, data),
  update: (id: number, data: Partial<ApiModule>) => request.patch<ApiModule>(`${BASE_URL}/modules/${id}/`, data),
  delete: (id: number) => request.delete(`${BASE_URL}/modules/${id}/`),
}

export const apiEnvApi = {
  list: (params?: { project?: number; search?: string }) =>
    request.get<PaginatedResponse<ApiEnvironmentConfig>>(`${BASE_URL}/env-configs/`, { params }),
  create: (data: Partial<ApiEnvironmentConfig>) => request.post<ApiEnvironmentConfig>(`${BASE_URL}/env-configs/`, data),
  update: (id: number, data: Partial<ApiEnvironmentConfig>) =>
    request.patch<ApiEnvironmentConfig>(`${BASE_URL}/env-configs/${id}/`, data),
  delete: (id: number) => request.delete(`${BASE_URL}/env-configs/${id}/`),
}

export const apiDefinitionApi = {
  list: (params?: { project?: number; module?: number; method?: string; search?: string }) =>
    request.get<PaginatedResponse<ApiDefinition>>(`${BASE_URL}/definitions/`, { params }),
  retrieve: (id: number) => request.get<ApiDefinition>(`${BASE_URL}/definitions/${id}/`),
  create: (data: Partial<ApiDefinition>) => request.post<ApiDefinition>(`${BASE_URL}/definitions/`, data),
  update: (id: number, data: Partial<ApiDefinition>) =>
    request.patch<ApiDefinition>(`${BASE_URL}/definitions/${id}/`, data),
  delete: (id: number) => request.delete(`${BASE_URL}/definitions/${id}/`),
  generateCase: (id: number, data?: { module?: number; environment?: number }) =>
    request.post(`${BASE_URL}/definitions/${id}/generate-case/`, data || {}),
  importOpenApi: (data: FormData | Record<string, unknown>) =>
    request.post(`${BASE_URL}/definitions/import-openapi/`, data),
}

export const apiCaseApi = {
  list: (params?: { project?: number; module?: number; status?: number; search?: string }) =>
    request.get<PaginatedResponse<ApiTestCase>>(`${BASE_URL}/testcases/`, { params }),
  create: (data: Partial<ApiTestCase>) => request.post<ApiTestCase>(`${BASE_URL}/testcases/`, data),
  update: (id: number, data: Partial<ApiTestCase>) => request.patch<ApiTestCase>(`${BASE_URL}/testcases/${id}/`, data),
  delete: (id: number) => request.delete(`${BASE_URL}/testcases/${id}/`),
  execute: (id: number, data?: { environment?: number }) => request.post(`${BASE_URL}/testcases/${id}/execute/`, data || {}),
  batchExecute: (data: { project: number; case_ids: number[]; environment?: number; name?: string }) =>
    request.post(`${BASE_URL}/testcases/batch-execute/`, data),
  generateFromFunctionalCase: (data: Record<string, unknown>) =>
    request.post(`${BASE_URL}/testcases/generate-from-functional-case/`, data),
  generateFromUiTrace: (data: Record<string, unknown>) =>
    request.post(`${BASE_URL}/testcases/generate-from-ui-trace/`, data),
  aiEnhance: (id: number, data?: { apply?: boolean }) =>
    request.post(`${BASE_URL}/testcases/${id}/ai-enhance/`, data || {}),
}

export const apiPublicDataApi = {
  list: (params?: { project?: number; search?: string; is_enabled?: boolean }) =>
    request.get<PaginatedResponse<ApiPublicData>>(`${BASE_URL}/public-data/`, { params }),
  create: (data: Partial<ApiPublicData>) => request.post<ApiPublicData>(`${BASE_URL}/public-data/`, data),
  update: (id: number, data: Partial<ApiPublicData>) => request.patch<ApiPublicData>(`${BASE_URL}/public-data/${id}/`, data),
  delete: (id: number) => request.delete(`${BASE_URL}/public-data/${id}/`),
}

export const apiScriptApi = {
  list: (params?: { project?: number; module?: number; script_type?: string }) =>
    request.get<PaginatedResponse<ApiScript>>(`${BASE_URL}/scripts/`, { params }),
  create: (data: Partial<ApiScript>) => request.post<ApiScript>(`${BASE_URL}/scripts/`, data),
  update: (id: number, data: Partial<ApiScript>) => request.patch<ApiScript>(`${BASE_URL}/scripts/${id}/`, data),
  delete: (id: number) => request.delete(`${BASE_URL}/scripts/${id}/`),
}

export const apiRecordApi = {
  list: (params?: { project?: number; status?: number; trigger_type?: string }) =>
    request.get<PaginatedResponse<ApiExecutionRecord>>(`${BASE_URL}/execution-records/`, { params }),
  batches: (params?: { project?: number; status?: number; trigger_type?: string }) =>
    request.get<PaginatedResponse<ApiBatchExecutionRecord>>(`${BASE_URL}/batch-records/`, { params }),
  getBatch: (id: number) => request.get<ApiBatchExecutionRecord>(`${BASE_URL}/batch-records/${id}/`),
}

