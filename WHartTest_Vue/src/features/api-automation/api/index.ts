import request from '@/utils/request'
import type {
  ApiBatchExecutionRecord,
  ApiCustomFunction,
  ApiDefinition,
  ApiEnvironmentConfig,
  ApiExecutionRecord,
  ApiModule,
  ApiPublicData,
  ApiScenario,
  ApiScenarioExecutionRecord,
  ApiScript,
  ApiScenarioStep,
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
  list: (params?: { project?: number; search?: string; page_size?: number }) =>
    request.get<PaginatedResponse<ApiEnvironmentConfig>>(`${BASE_URL}/env-configs/`, { params }),
  create: (data: Partial<ApiEnvironmentConfig>) => request.post<ApiEnvironmentConfig>(`${BASE_URL}/env-configs/`, data),
  update: (id: number, data: Partial<ApiEnvironmentConfig>) =>
    request.patch<ApiEnvironmentConfig>(`${BASE_URL}/env-configs/${id}/`, data),
  delete: (id: number) => request.delete(`${BASE_URL}/env-configs/${id}/`),
}

export const apiDefinitionApi = {
  list: (params?: { project?: number; module?: number; method?: string; search?: string; page_size?: number }) =>
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
  list: (params?: { project?: number; module?: number; environment?: number; status?: number; search?: string; page_size?: number }) =>
    request.get<PaginatedResponse<ApiTestCase>>(`${BASE_URL}/testcases/`, { params }),
  retrieve: (id: number) => request.get<ApiTestCase>(`${BASE_URL}/testcases/${id}/`),
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
  aiEnhance: (id: number, data?: { apply?: boolean; suggested?: Record<string, unknown> }) =>
    request.post(`${BASE_URL}/testcases/${id}/ai-enhance/`, data || {}),
  batchAiEnhance: (data: {
    case_ids: number[]
    apply?: boolean
    mode?: 'accurate' | 'fast'
    items?: Array<Record<string, unknown>>
  }) => request.post(`${BASE_URL}/testcases/batch-ai-enhance/`, data),
}

export const apiPublicDataApi = {
  list: (params?: { project?: number; search?: string; is_enabled?: boolean; page_size?: number }) =>
    request.get<PaginatedResponse<ApiPublicData>>(`${BASE_URL}/public-data/`, { params }),
  create: (data: Partial<ApiPublicData>) => request.post<ApiPublicData>(`${BASE_URL}/public-data/`, data),
  update: (id: number, data: Partial<ApiPublicData>) => request.patch<ApiPublicData>(`${BASE_URL}/public-data/${id}/`, data),
  delete: (id: number) => request.delete(`${BASE_URL}/public-data/${id}/`),
}

export const apiScenarioApi = {
  list: (params?: { project?: number; module?: number; status?: number; search?: string; page_size?: number }) =>
    request.get<PaginatedResponse<ApiScenario>>(`${BASE_URL}/scenarios/`, { params }),
  retrieve: (id: number) => request.get<ApiScenario>(`${BASE_URL}/scenarios/${id}/`),
  create: (data: Partial<ApiScenario> & { steps?: ApiScenarioStep[] }) =>
    request.post<ApiScenario>(`${BASE_URL}/scenarios/`, data),
  update: (id: number, data: Partial<ApiScenario> & { steps?: ApiScenarioStep[] }) =>
    request.patch<ApiScenario>(`${BASE_URL}/scenarios/${id}/`, data),
  delete: (id: number) => request.delete(`${BASE_URL}/scenarios/${id}/`),
  execute: (id: number, data?: { environment?: number }) => request.post(`${BASE_URL}/scenarios/${id}/execute/`, data || {}),
  batchExecute: (scenarioIds: number[], data?: { environment?: number }) =>
    request.post(`${BASE_URL}/scenarios/batch-execute/`, { scenario_ids: scenarioIds, ...(data || {}) }),
}

export const apiCustomFunctionApi = {
  list: (params?: { project?: number; is_active?: boolean; search?: string; page_size?: number }) =>
    request.get<PaginatedResponse<ApiCustomFunction>>(`${BASE_URL}/custom-functions/`, { params }),
  create: (data: Partial<ApiCustomFunction>) => request.post<ApiCustomFunction>(`${BASE_URL}/custom-functions/`, data),
  update: (id: number, data: Partial<ApiCustomFunction>) =>
    request.patch<ApiCustomFunction>(`${BASE_URL}/custom-functions/${id}/`, data),
  delete: (id: number) => request.delete(`${BASE_URL}/custom-functions/${id}/`),
}

export const apiScriptApi = {
  list: (params?: { project?: number; module?: number; script_type?: string; page_size?: number }) =>
    request.get<PaginatedResponse<ApiScript>>(`${BASE_URL}/scripts/`, { params }),
  create: (data: Partial<ApiScript>) => request.post<ApiScript>(`${BASE_URL}/scripts/`, data),
  update: (id: number, data: Partial<ApiScript>) => request.patch<ApiScript>(`${BASE_URL}/scripts/${id}/`, data),
  delete: (id: number) => request.delete(`${BASE_URL}/scripts/${id}/`),
}

export const apiRecordApi = {
  list: (params?: { project?: number; status?: number; trigger_type?: string; page_size?: number }) =>
    request.get<PaginatedResponse<ApiExecutionRecord>>(`${BASE_URL}/execution-records/`, { params }),
  getRecord: (id: number) => request.get<ApiExecutionRecord>(`${BASE_URL}/execution-records/${id}/`),
  batches: (params?: { project?: number; status?: number; trigger_type?: string; page_size?: number }) =>
    request.get<PaginatedResponse<ApiBatchExecutionRecord>>(`${BASE_URL}/batch-records/`, { params }),
  getBatch: (id: number) => request.get<ApiBatchExecutionRecord>(`${BASE_URL}/batch-records/${id}/`),
  stats: (params?: { project?: number; module?: number }) =>
    request.get(`${BASE_URL}/execution-records/stats/`, { params }),
  scenarios: (params?: { project?: number; scenario?: number; status?: number; trigger_type?: string; page_size?: number }) =>
    request.get<PaginatedResponse<ApiScenarioExecutionRecord>>(`${BASE_URL}/scenario-records/`, { params }),
  getScenarioRecord: (id: number) => request.get<ApiScenarioExecutionRecord>(`${BASE_URL}/scenario-records/${id}/`),
}
