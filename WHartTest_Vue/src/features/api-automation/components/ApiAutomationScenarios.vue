<template>
  <div class="api-scenario-panel">
    <div class="toolbar">
      <a-input-search v-model="search" placeholder="搜索场景名称/描述" allow-clear @search="fetchScenarios" @clear="fetchScenarios" />
      <a-button type="primary" @click="openScenarioModal()">新增接口场景</a-button>
    </div>

    <a-table :columns="scenarioColumns" :data="scenarios" :loading="loading" :pagination="{ pageSize: 20, showTotal: true }" :scroll="{ x: 1000 }">
      <template #scenario_status="{ record }">
        <a-tag :color="record.status === 2 ? 'green' : record.status === 3 ? 'red' : record.status === 1 ? 'arcoblue' : 'gray'">
          {{ STATUS_LABELS[record.status] }}
        </a-tag>
      </template>
      <template #scenario_steps="{ record }">{{ record.step_count || record.steps?.length || 0 }}</template>
      <template #scenario_created="{ record }">{{ formatDateTime(record.created_at) }}</template>
      <template #scenario_ops="{ record }">
        <a-space size="mini">
          <a-button type="text" size="mini" @click="executeScenario(record)">执行</a-button>
          <a-button type="text" size="mini" @click="openScenarioModal(record)">编辑</a-button>
          <a-popconfirm content="确认删除该接口场景？" @ok="handleDeleteScenario(record)">
            <a-button type="text" size="mini" status="danger">删除</a-button>
          </a-popconfirm>
        </a-space>
      </template>
    </a-table>

    <div class="scenario-record-header">场景执行记录</div>
    <a-table
      :columns="recordColumns"
      :data="scenarioRecords"
      :loading="recordLoading"
      :pagination="{ pageSize: 20, showTotal: true }"
      row-key="id"
      :expandable="{ expandedRowRender: renderExpanded }"
      :scroll="{ x: 1100 }"
    >
      <template #record_status="{ record }">
        <a-tag :color="record.status === 2 ? 'green' : record.status === 3 ? 'red' : record.status === 1 ? 'arcoblue' : 'gray'">
          {{ STATUS_LABELS[record.status] }}
        </a-tag>
      </template>
      <template #record_created="{ record }">{{ formatDateTime(record.created_at) }}</template>
      <template #record_duration="{ record }">{{ formatDuration(record.duration) }}</template>
      <template #record_summary="{ record }">
        {{ summarizeRecord(record) }}
      </template>
    </a-table>

    <a-modal
      v-model:visible="scenarioModalVisible"
      :title="editingScenarioId ? '编辑接口场景' : '新增接口场景'"
      :width="980"
      @before-ok="submitScenario"
    >
      <a-form layout="vertical">
        <a-form-item label="场景名称" required>
          <a-input v-model="scenarioForm.name" />
        </a-form-item>
        <a-form-item label="所属模块" required>
          <a-select v-model="scenarioForm.module" :options="moduleOptions" allow-search placeholder="选择角色或 Tab 模块" />
        </a-form-item>
        <a-form-item label="场景描述">
          <a-textarea v-model="scenarioForm.description" :auto-size="{ minRows: 2, maxRows: 4 }" />
        </a-form-item>
        <a-form-item>
          <template #label>
            <span class="scenario-label-with-tip">
              步骤列表
              <a-tooltip content="一个场景就是一条业务流程。按顺序选择已有接口用例，执行时会自动共享变量上下文，前一步提取出的变量可直接给后一步使用。">
                <icon-info-circle class="scenario-help-icon" />
              </a-tooltip>
            </span>
          </template>
          <div class="scenario-step-stage">
            <div class="scenario-step-helper">
              建议按 01 登录、02 列表、03 详情、04 创建 这种顺序编排；拖住左侧手柄可上下调整顺序。
            </div>
            <draggable
              v-model="scenarioSteps"
              item-key="client_key"
              handle=".scenario-drag-handle"
              ghost-class="scenario-step-ghost"
              chosen-class="scenario-step-chosen"
              :animation="180"
              class="scenario-step-list"
              @end="normalizeStepOrders"
            >
              <template #item="{ element: step, index }">
                <div class="scenario-step-card">
                  <div class="scenario-step-top">
                    <div class="scenario-step-head">
                      <button type="button" class="scenario-drag-handle" aria-label="拖动排序">
                        <icon-drag-dot-vertical />
                      </button>
                      <div class="scenario-step-index">步骤 {{ String(index + 1).padStart(2, '0') }}</div>
                    </div>
                    <div class="scenario-step-actions">
                      <a-button size="mini" type="text" status="danger" @click="removeStep(index)">删除</a-button>
                    </div>
                  </div>
                  <div class="scenario-step-grid">
                    <a-select
                      v-model="step.test_case"
                      :options="caseOptions"
                      allow-search
                      placeholder="选择接口用例"
                      @change="handleStepCaseChange(step)"
                    />
                    <a-input v-model="step.name" placeholder="可选：业务步骤名称，不填则默认显示接口用例名" />
                  </div>
                  <div class="scenario-step-preview" v-if="caseMap[step.test_case]">
                    <a-tag size="small" color="arcoblue">{{ caseMap[step.test_case].method }}</a-tag>
                    <span class="scenario-step-path">{{ caseMap[step.test_case].path }}</span>
                  </div>
                  <div class="scenario-step-vars" v-if="getStepExtractorNames(step).length">
                    <span class="scenario-step-vars-label">该步骤可向后传递：</span>
                    <a-tag v-for="name in getStepExtractorNames(step)" :key="name" size="small" color="green">
                      {{ formatVariableRef(name) }}
                    </a-tag>
                  </div>
                  <div class="scenario-step-vars scenario-step-vars--incoming" v-if="getInheritedVariableRefs(index).length">
                    <span class="scenario-step-vars-label">本步骤可直接引用：</span>
                    <a-tag
                      v-for="variableRef in getInheritedVariableRefs(index)"
                      :key="variableRef"
                      size="small"
                      color="arcoblue"
                      class="scenario-copy-tag"
                      @click="copyVariableRef(variableRef)"
                    >
                      {{ variableRef }}
                    </a-tag>
                  </div>
                  <div class="scenario-step-meta">
                    <a-checkbox v-model="step.is_enabled">启用该步骤</a-checkbox>
                    <a-checkbox v-model="step.stop_on_failure">失败即停止</a-checkbox>
                    <span class="scenario-step-meta-text">在路径、请求头、Query、Body 里可直接引用变量，如 {{ formatVariableRef('profile_id') }}。</span>
                  </div>
                  <div class="scenario-step-insert">
                    <a-button size="small" type="outline" @click="insertStep(index)">在此步骤下新增下一步</a-button>
                  </div>
                </div>
              </template>
            </draggable>
            <div v-if="!scenarioSteps.length" class="scenario-step-empty">
              <div class="scenario-step-empty-copy">还没有步骤，先新增第一步。</div>
              <a-button size="small" type="outline" @click="addStep">新增第一步</a-button>
            </div>
          </div>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, h, reactive, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconDragDotVertical, IconInfoCircle } from '@arco-design/web-vue/es/icon'
import draggable from 'vuedraggable'
import { apiCaseApi, apiRecordApi, apiScenarioApi } from '../api'
import type {
  ApiEnvironmentConfig,
  ApiScenario,
  ApiScenarioExecutionRecord,
  ApiScenarioStep,
  ApiScenarioStepRecord,
  ApiTestCase,
} from '../types'
import { STATUS_LABELS, unwrapData, unwrapPage } from '../types'

const props = defineProps<{
  projectId?: number
  selectedModuleId?: number
  moduleOptions: Array<{ label: string; value: number }>
  envConfigs: ApiEnvironmentConfig[]
}>()

const loading = ref(false)
const recordLoading = ref(false)
const submitting = ref(false)
const search = ref('')
const scenarios = ref<ApiScenario[]>([])
const scenarioRecords = ref<ApiScenarioExecutionRecord[]>([])
const scenarioModalVisible = ref(false)
const editingScenarioId = ref<number | null>(null)
const scenarioSteps = ref<ApiScenarioStep[]>([])
const selectableCases = ref<ApiTestCase[]>([])

const scenarioForm = reactive({
  name: '',
  module: undefined as number | undefined,
  description: '',
})

const createEmptyStep = (order: number): ApiScenarioStep & { client_key: string } => ({
  client_key: `step-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  order,
  test_case: 0,
  name: '',
  is_enabled: true,
  stop_on_failure: true,
})

const caseOptions = computed(() =>
  selectableCases.value.map((item) => ({
    label: `${item.name} (${item.method} ${item.path})`,
    value: item.id,
  })),
)
const caseMap = computed<Record<number, ApiTestCase>>(() =>
  selectableCases.value.reduce((acc, item) => {
    acc[item.id] = item
    return acc
  }, {} as Record<number, ApiTestCase>),
)

const scenarioColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '场景名称', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '模块', dataIndex: 'module_name', width: 180, ellipsis: true, tooltip: true },
  { title: '步骤数', slotName: 'scenario_steps', width: 90 },
  { title: '状态', slotName: 'scenario_status', width: 90 },
  { title: '创建时间', slotName: 'scenario_created', width: 180 },
  { title: '操作', slotName: 'scenario_ops', width: 180 },
]

const recordColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '场景名称', dataIndex: 'scenario_name', ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'record_status', width: 90 },
  { title: '创建时间', slotName: 'record_created', width: 180 },
  { title: '耗时', slotName: 'record_duration', width: 100 },
  { title: '结果概览', slotName: 'record_summary', ellipsis: true, tooltip: true },
]

const formatDateTime = (value?: string | null) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const pad = (num: number) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

const formatDuration = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toFixed(3)} s`
}

const formatVariableRef = (name?: string | null) => `\${{${name || ''}}}`

const summarizeRecord = (record: ApiScenarioExecutionRecord) => {
  const summary = (record.result_summary || {}) as Record<string, any>
  if (!summary.total_steps) return record.error_message || '-'
  return `通过 ${summary.passed_steps || 0}/${summary.total_steps}，失败 ${summary.failed_steps || 0}`
}

const renderExpanded = (payload: { record?: ApiScenarioExecutionRecord } | ApiScenarioExecutionRecord) => {
  const record = (payload as { record?: ApiScenarioExecutionRecord })?.record ?? (payload as ApiScenarioExecutionRecord)
  if (!record) return h('div', { class: 'scenario-record-expand' }, [])
  const items = (record.step_records || []) as ApiScenarioStepRecord[]
  return h(
    'div',
    { class: 'scenario-record-expand' },
    items.map((item) =>
      h('div', { class: 'scenario-record-step', key: item.id }, [
        h('div', { class: 'scenario-record-step-head' }, `${item.order}. ${item.step_name || item.test_case_name || '-'}`),
        h('div', { class: 'scenario-record-step-meta' }, [
          h('span', null, `状态：${STATUS_LABELS[item.status] || '-'}`),
          h('span', null, `耗时：${formatDuration(item.duration)}`),
          h('span', null, item.error_message ? `错误：${item.error_message}` : '错误：-'),
        ]),
        item.extracted_variables && Object.keys(item.extracted_variables).length
          ? h(
              'div',
              { class: 'scenario-record-step-vars' },
              Object.entries(item.extracted_variables).map(([key, value]) =>
                h('span', { class: 'scenario-record-step-var', key }, `${formatVariableRef(key)} = ${String(value)}`),
              ),
            )
          : null,
      ]),
    ),
  )
}

const fetchScenarios = async () => {
  if (!props.projectId) return
  loading.value = true
  try {
    const res = await apiScenarioApi.list({
      project: props.projectId,
      module: props.selectedModuleId || undefined,
      search: search.value || undefined,
    })
    scenarios.value = unwrapPage<ApiScenario>(res).items
  } finally {
    loading.value = false
  }
}

const fetchRecords = async () => {
  if (!props.projectId) return
  recordLoading.value = true
  try {
    const res = await apiRecordApi.scenarios({ project: props.projectId })
    scenarioRecords.value = unwrapPage<ApiScenarioExecutionRecord>(res).items
  } finally {
    recordLoading.value = false
  }
}

const fetchSelectableCases = async () => {
  if (!props.projectId) return
  const res = await apiCaseApi.list({ project: props.projectId, module: props.selectedModuleId || undefined, search: undefined, page_size: 500 } as any)
  selectableCases.value = unwrapPage<ApiTestCase>(res).items
}

const resetForm = () => {
  editingScenarioId.value = null
  scenarioForm.name = ''
  scenarioForm.module = props.selectedModuleId
  scenarioForm.description = ''
  scenarioSteps.value = []
}

const normalizeStepOrders = () => {
  scenarioSteps.value = scenarioSteps.value.map((item, index) => ({
    ...item,
    order: index + 1,
  }))
}

const openScenarioModal = async (record?: ApiScenario) => {
  await fetchSelectableCases()
  if (!record) {
    resetForm()
    scenarioModalVisible.value = true
    if (!scenarioSteps.value.length) addStep()
    return
  }
  const detail = unwrapData<ApiScenario>(await apiScenarioApi.retrieve(record.id))
  editingScenarioId.value = detail.id
  scenarioForm.name = detail.name
  scenarioForm.module = detail.module
  scenarioForm.description = detail.description || ''
  scenarioSteps.value = (detail.steps || []).map((step) => ({
    client_key: `step-${step.id || step.order}-${Math.random().toString(36).slice(2, 8)}`,
    id: step.id,
    order: step.order,
    test_case: step.test_case,
    name: step.name || '',
    is_enabled: step.is_enabled,
    stop_on_failure: step.stop_on_failure,
  }))
  scenarioModalVisible.value = true
}

const addStep = () => {
  scenarioSteps.value.push(createEmptyStep(scenarioSteps.value.length + 1))
  normalizeStepOrders()
}

const insertStep = (index: number) => {
  const next = [...scenarioSteps.value]
  next.splice(index + 1, 0, createEmptyStep(index + 2))
  scenarioSteps.value = next
  normalizeStepOrders()
}

const removeStep = (index: number) => {
  scenarioSteps.value.splice(index, 1)
  normalizeStepOrders()
}

const handleStepCaseChange = (step: ApiScenarioStep) => {
  if (!step.name?.trim()) {
    const current = caseMap.value[step.test_case]
    if (current) step.name = current.name
  }
}

const getStepExtractorNames = (step: ApiScenarioStep) => {
  const current = caseMap.value[step.test_case]
  const extractors = Array.isArray(current?.extractors) ? current.extractors : []
  return extractors.map((item: any) => String(item?.name || '').trim()).filter(Boolean).slice(0, 6)
}

const getInheritedVariableRefs = (index: number) => {
  const refs: string[] = []
  const seen = new Set<string>()
  for (let currentIndex = 0; currentIndex < index; currentIndex += 1) {
    for (const name of getStepExtractorNames(scenarioSteps.value[currentIndex])) {
      const ref = formatVariableRef(name)
      if (!seen.has(ref)) {
        seen.add(ref)
        refs.push(ref)
      }
    }
  }
  return refs
}

const copyVariableRef = async (value: string) => {
  try {
    await navigator.clipboard.writeText(value)
    Message.success(`已复制变量 ${value}`)
  } catch {
    Message.warning('复制失败，请手动复制')
  }
}

const submitScenario = async () => {
  if (!props.projectId) return false
  if (!scenarioForm.name.trim() || !scenarioForm.module) {
    Message.warning('请填写场景名称并选择模块')
    return false
  }
  const steps = scenarioSteps.value
    .filter((item) => item.test_case)
    .map((item, index) => ({
      order: index + 1,
      test_case: item.test_case,
      name: item.name || '',
      is_enabled: item.is_enabled,
      stop_on_failure: item.stop_on_failure,
    }))
  if (!steps.length) {
    Message.warning('请至少添加一个接口步骤')
    return false
  }
  submitting.value = true
  try {
    const payload = {
      project: props.projectId,
      module: scenarioForm.module,
      name: scenarioForm.name.trim(),
      description: scenarioForm.description || '',
      steps,
    }
    if (editingScenarioId.value) await apiScenarioApi.update(editingScenarioId.value, payload)
    else await apiScenarioApi.create(payload)
    Message.success('接口场景已保存')
    scenarioModalVisible.value = false
    await Promise.all([fetchScenarios(), fetchRecords()])
    return true
  } finally {
    submitting.value = false
  }
}

const executeScenario = async (record: ApiScenario) => {
  const res = await apiScenarioApi.execute(record.id)
  Message.loading({ content: '接口场景执行中...', duration: 0 } as any)
  const recordId = unwrapData<any>(res)?.record_id || res.data?.record_id
  if (!recordId) {
    Message.clear()
    Message.error('场景提交失败')
    return
  }
  for (let attempt = 0; attempt < 45; attempt += 1) {
    const detail = unwrapData<ApiScenarioExecutionRecord>(await apiRecordApi.getScenarioRecord(recordId))
    if (detail && [2, 3].includes(detail.status)) {
      Message.clear()
      Message[detail.status === 2 ? 'success' : 'error'](`接口场景执行${detail.status === 2 ? '成功' : '失败'}`)
      await Promise.all([fetchScenarios(), fetchRecords()])
      return
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
  }
  Message.clear()
  Message.warning('接口场景执行超时，请稍后查看记录')
  await fetchRecords()
}

const handleDeleteScenario = async (record: ApiScenario) => {
  await apiScenarioApi.delete(record.id)
  Message.success('接口场景已删除')
  await Promise.all([fetchScenarios(), fetchRecords()])
}

watch(() => [props.projectId, props.selectedModuleId], () => {
  fetchScenarios()
  fetchRecords()
}, { immediate: true })
</script>

<style scoped>
.api-scenario-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.scenario-record-header {
  font-weight: 600;
  margin-top: 8px;
}

.scenario-step-stage {
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
}

.scenario-step-helper {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(var(--theme-accent-rgb), 0.08);
  color: var(--color-text-2);
  font-size: 12px;
  line-height: 1.6;
}

.scenario-step-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 20px 12px;
  border: 1px dashed rgba(var(--theme-accent-rgb), 0.2);
  border-radius: 12px;
  margin-bottom: 12px;
  background: rgba(var(--theme-accent-rgb), 0.03);
}

.scenario-step-empty-copy {
  color: var(--color-text-3);
  font-size: 12px;
}

.scenario-step-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.scenario-step-card {
  border: 1px solid rgba(var(--theme-accent-rgb), 0.18);
  border-radius: 12px;
  padding: 14px;
  background: linear-gradient(180deg, rgba(var(--theme-accent-rgb), 0.06), rgba(var(--theme-accent-rgb), 0.02));
  width: 100%;
}

.scenario-step-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.scenario-step-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.scenario-step-index {
  font-weight: 700;
  color: var(--theme-accent);
}

.scenario-drag-handle {
  border: none;
  background: rgba(var(--theme-accent-rgb), 0.14);
  color: var(--theme-accent);
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
}

.scenario-drag-handle:active {
  cursor: grabbing;
}

.scenario-step-ghost {
  opacity: 0.55;
}

.scenario-step-chosen {
  border-color: rgba(var(--theme-accent-rgb), 0.45);
  box-shadow: 0 10px 30px rgba(var(--theme-accent-rgb), 0.12);
}

.scenario-step-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.scenario-step-grid {
  display: grid;
  grid-template-columns: minmax(280px, 1.2fr) minmax(220px, 1fr);
  gap: 12px;
  align-items: center;
}

.scenario-step-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  color: var(--color-text-2);
}

.scenario-step-vars {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
}

.scenario-step-vars-label {
  color: var(--color-text-3);
  font-size: 12px;
}

.scenario-step-vars--incoming {
  margin-top: 8px;
}

.scenario-copy-tag {
  cursor: pointer;
}

.scenario-step-path {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  word-break: break-all;
}

.scenario-step-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
  color: var(--color-text-3);
}

.scenario-step-meta-text {
  font-size: 12px;
}

.scenario-step-insert {
  display: flex;
  justify-content: center;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed rgba(var(--theme-accent-rgb), 0.18);
}

.scenario-label-with-tip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.scenario-help-icon {
  color: var(--theme-accent);
  cursor: pointer;
}

.scenario-record-expand {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.scenario-record-step {
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--color-fill-2);
}

.scenario-record-step-head {
  font-weight: 600;
  margin-bottom: 4px;
}

.scenario-record-step-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: var(--color-text-3);
}

.scenario-record-step-vars {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.scenario-record-step-var {
  font-size: 12px;
  color: var(--theme-accent);
  background: rgba(var(--theme-accent-rgb), 0.08);
  border: 1px solid rgba(var(--theme-accent-rgb), 0.2);
  border-radius: 999px;
  padding: 2px 8px;
}

@media (max-width: 960px) {
  .scenario-step-stage {
    max-width: 100%;
  }

  .scenario-step-grid {
    grid-template-columns: 1fr;
  }

  .scenario-step-top {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
