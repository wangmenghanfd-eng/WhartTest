<template>
  <a-modal
    v-model:visible="visibleProxy"
    title="功能用例 AI 生成接口用例"
    :width="960"
    :ok-loading="submitting"
    :ok-button-props="{ disabled: !canSubmit }"
    @before-ok="handleSubmit"
    @cancel="handleCancel"
  >
    <a-alert type="info" closable style="margin-bottom: 12px;">
      会把功能用例的标题/前置/步骤交给已激活的 LLM，让它输出可入库的接口用例草稿。如果项目里有 OpenAPI 定义，LLM 会优先匹配这些定义。
    </a-alert>

    <a-form layout="vertical">
      <a-form-item label="功能用例" required>
        <a-select
          v-model="form.testcaseId"
          placeholder="选择需要翻译的功能用例"
          allow-search
          allow-clear
          :loading="caseLoading"
          @change="onCaseChange"
        >
          <a-option v-for="c in functionalCases" :key="c.id" :value="c.id">
            #{{ c.id }} · {{ c.name }} · {{ c.level || '-' }}
          </a-option>
        </a-select>
      </a-form-item>

      <a-form-item label="目标接口模块" required>
        <a-select
          v-model="form.moduleId"
          placeholder="新建用例存放在哪个接口模块"
          :options="moduleOptions"
          allow-search
          allow-clear
        />
      </a-form-item>

      <a-form-item label="环境（可选）">
        <a-select v-model="form.environmentId" placeholder="不选则使用默认环境" allow-clear>
          <a-option v-for="env in envConfigs" :key="env.id" :value="env.id">
            {{ env.name }}
          </a-option>
        </a-select>
      </a-form-item>

      <a-form-item>
        <a-button type="primary" :loading="previewLoading" :disabled="!form.testcaseId" @click="loadCandidates">
          调用 AI 生成预览
        </a-button>
        <span v-if="hasLoaded" style="margin-left: 12px; color: var(--color-text-3);">
          共 {{ candidates.length }} 个候选，已选 {{ selectedRowKeys.length }}
        </span>
        <span v-if="lastError" style="margin-left: 12px; color: var(--color-danger);">{{ lastError }}</span>
      </a-form-item>

      <a-table
        v-if="candidates.length"
        row-key="index"
        :row-selection="{ type: 'checkbox', showCheckedAll: true }"
        v-model:selected-keys="selectedRowKeys"
        :data="candidates"
        :columns="columns"
        :pagination="false"
        :scroll="{ y: 280, x: 800 }"
        size="small"
      >
        <template #method="{ record }">
          <a-tag :color="methodColor(record.method)">{{ record.method }}</a-tag>
        </template>
        <template #path="{ record }">
          <a-tooltip :content="record.rationale">
            <span>{{ record.path }}</span>
          </a-tooltip>
        </template>
        <template #assertions="{ record }">
          <a-tag v-for="(a, i) in record.assertions || []" :key="i" size="small">
            {{ a.type }} {{ a.operator }} {{ a.expected }}
          </a-tag>
        </template>
      </a-table>
      <a-alert v-else-if="hasLoaded" type="warning">没有可用的候选。可能 LLM 未激活、或返回内容无法解析。</a-alert>
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

const visibleProxy = computed<boolean>({
  get: () => props.visible,
  set: (value) => emit('update:visible', value),
})

const form = ref({
  testcaseId: undefined as number | undefined,
  moduleId: undefined as number | undefined,
  environmentId: undefined as number | undefined,
})
const candidates = ref<Array<Record<string, any>>>([])
const selectedRowKeys = ref<number[]>([])
const caseLoading = ref(false)
const previewLoading = ref(false)
const submitting = ref(false)
const hasLoaded = ref(false)
const lastError = ref('')
const functionalCases = ref<Array<Record<string, any>>>([])
const envConfigs = ref<ApiEnvironmentConfig[]>([])

const columns = [
  { title: '#', dataIndex: 'index', width: 50 },
  { title: '名称', dataIndex: 'name', ellipsis: true, tooltip: true, width: 220 },
  { title: '方法', slotName: 'method', width: 80 },
  { title: '路径', slotName: 'path', ellipsis: true },
  { title: '断言', slotName: 'assertions', width: 220 },
]

const canSubmit = computed(
  () => !!form.value.testcaseId && !!form.value.moduleId && selectedRowKeys.value.length > 0,
)

function methodColor(method: string) {
  switch (method) {
    case 'GET': return 'arcoblue'
    case 'POST': return 'green'
    case 'PUT': return 'orange'
    case 'DELETE': return 'red'
    case 'PATCH': return 'purple'
    default: return 'gray'
  }
}

async function fetchFunctionalCases() {
  if (!props.projectId) return
  caseLoading.value = true
  try {
    const res = await request.get(`/projects/${props.projectId}/testcases/`, {
      params: { page_size: 200 },
    })
    const items = unwrapPage<Record<string, any>>(res).items
    functionalCases.value = items
  } catch {
    Message.error('加载功能用例失败')
  } finally {
    caseLoading.value = false
  }
}

async function fetchEnvConfigs() {
  if (!props.projectId) return
  const res = await apiEnvApi.list({ project: props.projectId })
  envConfigs.value = unwrapPage<ApiEnvironmentConfig>(res).items
}

function onCaseChange() {
  candidates.value = []
  selectedRowKeys.value = []
  hasLoaded.value = false
  lastError.value = ''
}

async function loadCandidates() {
  if (!form.value.testcaseId) return
  previewLoading.value = true
  lastError.value = ''
  try {
    const res = await apiCaseApi.generateFromFunctionalCase({
      testcase_id: form.value.testcaseId,
      dry_run: true,
    })
    const data = unwrapData<any>(res)
    candidates.value = data?.candidates || []
    selectedRowKeys.value = candidates.value.map((c) => c.index)
    hasLoaded.value = true
    if (data?.error) lastError.value = data.error
  } catch (err: any) {
    lastError.value = err?.error || err?.message || '调用失败'
  } finally {
    previewLoading.value = false
  }
}

async function handleSubmit(done: (closed: boolean) => void) {
  if (!canSubmit.value) {
    Message.warning('请选择功能用例、目标模块并勾选至少一条候选')
    return done(false)
  }
  submitting.value = true
  try {
    const res = await apiCaseApi.generateFromFunctionalCase({
      testcase_id: form.value.testcaseId,
      dry_run: false,
      module: form.value.moduleId,
      environment: form.value.environmentId,
      selected_indexes: selectedRowKeys.value,
    })
    const data = unwrapData<any>(res)
    Message.success(`已创建 ${data?.created_count ?? 0} 个接口用例`)
    emit('imported')
    done(true)
  } catch (err: any) {
    Message.error(err?.error || '创建失败')
    done(false)
  } finally {
    submitting.value = false
  }
}

function handleCancel() {
  form.value = {
    testcaseId: undefined,
    moduleId: props.defaultModuleId,
    environmentId: undefined,
  }
  candidates.value = []
  selectedRowKeys.value = []
  hasLoaded.value = false
  lastError.value = ''
}

watch(
  () => props.visible,
  (v) => {
    if (v) {
      form.value.moduleId = props.defaultModuleId
      fetchFunctionalCases()
      fetchEnvConfigs()
    } else {
      handleCancel()
    }
  },
)
</script>
