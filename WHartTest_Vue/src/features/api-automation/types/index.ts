export interface PaginatedResponse<T> {
  count: number
  results: T[]
}

export interface ApiModule {
  id: number
  project: number
  name: string
  parent?: number | null
  level: number
  children?: ApiModule[]
}

export interface ApiEnvironmentConfig {
  id: number
  project: number
  name: string
  base_url: string
  headers: Record<string, string>
  variables: Record<string, string>
  is_default: boolean
}

export interface ApiDefinition {
  id: number
  project: number
  module: number
  module_name?: string
  name: string
  method: string
  path: string
  operation_id?: string
  source?: string
}

export interface ApiTestCase {
  id: number
  project: number
  module: number
  module_name?: string
  definition?: number | null
  environment?: number | null
  name: string
  method: string
  path: string
  headers: Record<string, string>
  query_params: Record<string, unknown>
  body: Record<string, unknown>
  assertions: Array<Record<string, unknown>>
  extractors: Array<Record<string, unknown>>
  status: number
  source?: string
}

export interface ApiPublicData {
  id: number
  project: number
  key: string
  value: string
  description?: string
  is_enabled: boolean
}

export interface ApiScript {
  id: number
  project: number
  module?: number | null
  name: string
  script_type: 'pre' | 'post'
  content: string
}

export interface ApiExecutionRecord {
  id: number
  test_case: number
  test_case_name?: string
  status: number
  trigger_type: 'manual' | 'scheduled'
  duration?: number | null
  error_message?: string
  request_data?: Record<string, unknown>
  response_data?: Record<string, unknown>
  created_at?: string
}

export interface ApiBatchExecutionRecord {
  id: number
  name: string
  status: number
  trigger_type: 'manual' | 'scheduled'
  total_cases: number
  passed_cases: number
  failed_cases: number
  success_rate: number
  duration?: number | null
  execution_records?: ApiExecutionRecord[]
  created_at?: string
}

export const STATUS_LABELS: Record<number, string> = {
  0: '未执行',
  1: '执行中',
  2: '成功',
  3: '失败',
}

export const BATCH_STATUS_LABELS: Record<number, string> = {
  0: '待执行',
  1: '执行中',
  2: '全部成功',
  3: '部分失败',
  4: '全部失败',
}

export function unwrapData<T>(res: any): T {
  return res?.data?.data ?? res?.data
}

export function unwrapPage<T>(res: any): { items: T[]; count: number } {
  const data = unwrapData<any>(res)
  if (Array.isArray(data)) return { items: data, count: data.length }
  return { items: data?.results ?? [], count: data?.count ?? 0 }
}

