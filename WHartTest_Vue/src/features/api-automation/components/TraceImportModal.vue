<template>
  <a-modal
    v-model:visible="visibleProxy"
    title="UI Trace 转接口用例"
    :width="900"
    :ok-loading="submitting"
    :ok-button-props="{ disabled: !canSubmit }"
    @before-ok="handleSubmit"
    @cancel="handleCancel"
  >
    <a-form layout="vertical">
      <a-form-item label="UI 用例(含 Trace 的执行)" required>
        <a-select
          v-model="form.executionRecordId"
          placeholder="选择带 Trace 的 UI 用例执行(需先跑一次并采集 Trace)"
          allow-search
          allow-clear
          :loading="recordLoading"
          @change="onRecordChange"
        >
          <a-option v-for="rec in executionRecords" :key="rec.id" :value="rec.id">
            {{ rec.test_case_name || ('用例#' + rec.test_case_id) }} · {{ STATUS_LABELS[rec.status] }} · {{ formatTime(rec.created_at) }}
          </a-option>
          <template #empty>
            <div style="padding: 8px 12px; color: var(--color-text-3);">暂无带 Trace 的执行记录 —— 请先执行一条采集了 Trace 的 UI 用例</div>
          </template>
        </a-select>
      </a-form-item>

      <a-form-item label="目标接口模块" required>
        <a-select
          v-model="form.moduleId"
          placeholder="选择导入目标模块"
          :options="moduleOptions"
          allow-search
          allow-clear
        />
      </a-form-item>

      <a-form-item label="指定环境（可选）">
        <a-select
          v-model="form.environmentId"
          placeholder="不选则按 base_url 自动查找/创建环境"
          allow-clear
          allow-search
        >
          <a-optgroup v-for="g in envGroups" :key="g.label" :label="g.label">
            <a-option v-for="env in g.envs" :key="env.id" :value="env.id">
              {{ env.name }} ({{ env.base_url || '—' }})
            </a-option>
          </a-optgroup>
        </a-select>
      </a-form-item>

      <a-form-item label="过滤静态资源">
        <a-switch v-model="form.skipStatic" />
      </a-form-item>

      <a-form-item>
        <a-button type="primary" :loading="previewLoading" :disabled="!form.executionRecordId" @click="loadCandidates">
          加载候选请求
        </a-button>
        <span v-if="candidates.length" style="margin-left: 12px; color: var(--color-text-3);">
          共 {{ candidates.length }} 个候选，已选 {{ selectedRowKeys.length }} 个
        </span>
      </a-form-item>

      <a-table
        v-if="candidates.length"
        row-key="index"
        :row-selection="{ type: 'checkbox', showCheckedAll: true }"
        v-model:selected-keys="selectedRowKeys"
        :data="candidates"
        :columns="columns"
        :pagination="false"
        :scroll="{ y: 280, x: 720 }"
        size="small"
      >
        <template #method="{ record }">
          <a-tag :color="methodColor(record.method)">{{ record.method }}</a-tag>
        </template>
        <template #path="{ record }">
          <a-tooltip :content="record.url">
            <span class="path-cell">{{ record.path }}</span>
          </a-tooltip>
        </template>
        <template #status="{ record }">
          <a-tag :color="record.response_status < 400 ? 'green' : 'red'">{{ record.response_status }}</a-tag>
        </template>
      </a-table>
      <a-alert v-else-if="hasLoaded" type="info">没有匹配的接口请求。可以关闭"过滤静态资源"重试。</a-alert>
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import request from '@/utils/request'
import { apiCaseApi, apiEnvApi } from '../api'
import { unwrapData, unwrapPage } from '../types'
import type { ApiEnvironmentConfig } from '../types'

const props = defineProps<{
  visible: boolean
  projectId: number | undefined
  moduleOptions: { label: string; value: number }[]
  defaultModuleId?: number
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'imported'): void
}>()

const STATUS_LABELS: Record<number, string> = {
  0: '未执行',
  1: '执行中',
  2: '成功',
  3: '失败',
  4: '取消',
}

const visibleProxy = computed<boolean>({
  get: () => props.visible,
  set: (value) => emit('update:visible', value),
})

const form = ref({
  executionRecordId: undefined as number | undefined,
  moduleId: undefined as number | undefined,
  environmentId: undefined as number | undefined,
  skipStatic: true,
})
const candidates = ref<Array<Record<string, any>>>([])
const selectedRowKeys = ref<number[]>([])
const recordLoading = ref(false)
const previewLoading = ref(false)
const submitting = ref(false)
const hasLoaded = ref(false)
const executionRecords = ref<Array<Record<string, any>>>([])
const envConfigs = ref<ApiEnvironmentConfig[]>([])

// 环境按类型分组(开发/测试/预发布/生产),下拉更清爽
const ENV_TYPE_ORDER: { key: string; label: string }[] = [
  { key: 'dev', label: '开发' },
  { key: 'test', label: '测试' },
  { key: 'staging', label: '预发布' },
  { key: 'prod', label: '生产' },
]
const envGroups = computed(() =>
  ENV_TYPE_ORDER.map((t) => ({
    label: t.label,
    envs: envConfigs.value.filter((e) => ((e as any).env_type || 'dev') === t.key),
  })).filter((g) => g.envs.length),
)

const columns = [
  { title: '#', dataIndex: 'index', width: 50 },
  { title: '方法', slotName: 'method', width: 80 },
  { title: '路径', slotName: 'path', ellipsis: true, tooltip: false },
  { title: '状态', slotName: 'status', width: 80 },
  { title: '大小', dataIndex: 'response_size', width: 80 },
]

const canSubmit = computed(
  () => !!form.value.executionRecordId && !!form.value.moduleId && selectedRowKeys.value.length > 0,
)

function methodColor(method: string) {
  switch (method) {
    case 'GET':
      return 'arcoblue'
    case 'POST':
      return 'green'
    case 'PUT':
      return 'orange'
    case 'DELETE':
      return 'red'
    case 'PATCH':
      return 'purple'
    default:
      return 'gray'
  }
}

function formatTime(value: string | undefined) {
  if (!value) return ''
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

async function fetchExecutionRecords() {
  if (!props.projectId) return
  recordLoading.value = true
  try {
    const res = await request.get('/ui-automation/execution-records/', {
      params: { project: props.projectId, has_trace: true },
    })
    const items = unwrapPage<Record<string, any>>(res).items
    executionRecords.value = items
  } catch (err: any) {
    Message.error('加载 UI 执行记录失败')
  } finally {
    recordLoading.value = false
  }
}

async function fetchEnvConfigs() {
  if (!props.projectId) return
  const res = await apiEnvApi.list({ project: props.projectId })
  envConfigs.value = unwrapPage<ApiEnvironmentConfig>(res).items
}

function onRecordChange() {
  candidates.value = []
  selectedRowKeys.value = []
  hasLoaded.value = false
}

async function loadCandidates() {
  if (!form.value.executionRecordId) return
  previewLoading.value = true
  try {
    const res = await apiCaseApi.generateFromUiTrace({
      execution_record_id: form.value.executionRecordId,
      dry_run: true,
      skip_static: form.value.skipStatic,
    })
    const data = unwrapData<any>(res)
    candidates.value = data?.candidates || []
    selectedRowKeys.value = candidates.value.map((c) => c.index)
    hasLoaded.value = true
  } catch (err: any) {
    Message.error(err?.error || '加载候选失败')
  } finally {
    previewLoading.value = false
  }
}

async function handleSubmit(done: (closed: boolean) => void) {
  if (!canSubmit.value) {
    Message.warning('请选择执行记录、目标模块并勾选至少一个候选请求')
    return done(false)
  }
  submitting.value = true
  try {
    const res = await apiCaseApi.generateFromUiTrace({
      execution_record_id: form.value.executionRecordId,
      dry_run: false,
      project: props.projectId,
      module: form.value.moduleId,
      environment: form.value.environmentId,
      selected_indexes: selectedRowKeys.value,
      skip_static: form.value.skipStatic,
    })
    const data = unwrapData<any>(res)
    Message.success(`已导入 ${data?.created_count ?? 0} 个接口用例`)
    emit('imported')
    done(true)
  } catch (err: any) {
    Message.error(err?.error || '导入失败')
    done(false)
  } finally {
    submitting.value = false
  }
}

function handleCancel() {
  form.value = {
    executionRecordId: undefined,
    moduleId: props.defaultModuleId,
    environmentId: undefined,
    skipStatic: true,
  }
  candidates.value = []
  selectedRowKeys.value = []
  hasLoaded.value = false
}

watch(
  () => props.visible,
  (v) => {
    if (v) {
      form.value.moduleId = props.defaultModuleId
      fetchExecutionRecords()
      fetchEnvConfigs()
    } else {
      handleCancel()
    }
  },
)
</script>

<style scoped>
.path-cell {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
