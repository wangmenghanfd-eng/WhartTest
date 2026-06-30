<template>
  <a-modal
    :visible="visible"
    :title="modalTitle"
    width="900px"
    :footer="false"
    @cancel="handleClose"
  >
    <template v-if="phase === 'form'">
      <a-form :model="formData" layout="vertical">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="录制目标" required>
              <a-select v-model="formData.target_type">
                <a-option value="test_case">录制生成用例</a-option>
                <a-option value="page_step">录制生成步骤</a-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="录制名称" required>
              <a-input v-model="formData.name" placeholder="请输入录制名称" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="所属模块" required>
              <a-select v-model="formData.module" placeholder="请选择模块">
                <a-option v-for="mod in moduleOptions" :key="mod.id" :value="mod.id">
                  {{ mod.name }}
                </a-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="执行环境">
              <a-select v-model="formData.env_config_id" allow-clear placeholder="请选择环境配置">
                <a-option v-for="env in envConfigs" :key="env.id" :value="env.id">
                  {{ env.name }}{{ env.is_default ? ' (默认)' : '' }}
                </a-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="执行器" required>
              <a-select v-model="formData.actuator_id" placeholder="请选择执行器">
                <a-option v-for="act in openActuators" :key="act.id" :value="act.id">
                  {{ act.name || act.id }}
                </a-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col v-if="formData.target_type === 'page_step'" :span="12">
            <a-form-item label="目标页面">
              <a-select v-model="formData.page" allow-clear placeholder="可选，不选时自动复用或创建页面">
                <a-option v-for="page in filteredPages" :key="page.id" :value="page.id">
                  {{ page.name }}
                </a-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-alert v-if="headlessSelected" type="warning" style="margin-top: 8px">
          当前环境配置为无头模式，录制需要可见浏览器。请切换到有头环境配置后再开始录制。
        </a-alert>
      </a-form>
    </template>

    <template v-else-if="phase === 'recording'">
      <div class="recording-state">
        <a-alert type="info">
          浏览器录制已启动，请在执行器弹出的浏览器中完成操作。结束后点击“停止录制并生成草稿”。
        </a-alert>
        <a-descriptions :column="2" style="margin-top: 16px">
          <a-descriptions-item label="录制名称">{{ currentSession?.name || formData.name }}</a-descriptions-item>
          <a-descriptions-item label="执行器">{{ selectedActuatorLabel }}</a-descriptions-item>
          <a-descriptions-item label="目标类型">{{ formData.target_type === 'test_case' ? '测试用例' : '页面步骤' }}</a-descriptions-item>
          <a-descriptions-item label="会话ID">{{ currentRecordingId || '-' }}</a-descriptions-item>
        </a-descriptions>
      </div>
    </template>

    <template v-else>
      <div v-if="currentSession" class="draft-preview">
        <a-alert
          v-if="currentSession.error_message"
          type="warning"
          style="margin-bottom: 16px"
        >
          {{ currentSession.error_message }}
        </a-alert>
        <a-alert
          v-if="currentSession.preview_payload?.warnings?.length"
          type="info"
          style="margin-bottom: 16px"
        >
          <div v-for="warning in currentSession.preview_payload.warnings" :key="warning">{{ warning }}</div>
        </a-alert>

        <a-descriptions :column="3" style="margin-bottom: 16px">
          <a-descriptions-item label="归一化动作">
            {{ editableActions.length }}
          </a-descriptions-item>
          <a-descriptions-item label="未支持语句">
            {{ currentSession.preview_payload?.summary?.unsupported_count ?? 0 }}
          </a-descriptions-item>
          <a-descriptions-item label="预计生成段数">
            {{ currentSession.preview_payload?.summary?.segment_count ?? 0 }}
          </a-descriptions-item>
        </a-descriptions>

        <a-alert type="info" style="margin-bottom: 16px">
          可以先在这里删除无效录制步骤，或修正定位、输入值和描述；保存后才会生成正式页面步骤/测试用例。
        </a-alert>

        <a-form layout="vertical" class="draft-editor">
          <a-form-item label="正式名称">
            <a-input v-model="draftName" placeholder="请输入保存后的名称" :max-length="255" />
          </a-form-item>
          <div class="editor-header">
            <strong>结构化动作编辑</strong>
            <a-button size="small" type="outline" @click="addDraftAction">新增动作</a-button>
          </div>
          <div v-if="editableActions.length" class="editable-action-list">
            <div v-for="(action, index) in editableActions" :key="action._key || `${index}-${action.line_no}`" class="editable-action-card">
              <div class="action-card-head">
                <a-tag color="arcoblue">#{{ index + 1 }}</a-tag>
                <a-select v-model="action.operation" class="operation-select" size="small">
                  <a-option v-for="op in operationOptions" :key="op.value" :value="op.value">
                    {{ op.label }}
                  </a-option>
                </a-select>
                <a-button type="text" status="danger" size="small" @click="removeDraftAction(index)">
                  删除
                </a-button>
              </div>
              <a-row :gutter="12">
                <a-col :xs="24" :sm="12">
                  <a-input v-model="action.description" size="small" placeholder="步骤描述" />
                </a-col>
                <a-col :xs="24" :sm="12">
                  <a-input v-model="action.value" size="small" placeholder="输入值 / 期望值 / URL" />
                </a-col>
              </a-row>
              <a-row :gutter="12" style="margin-top: 8px">
                <a-col :xs="24" :sm="8">
                  <a-select v-model="action.locator_type" size="small" allow-clear placeholder="定位类型">
                    <a-option v-for="loc in locatorTypeOptions" :key="loc.value" :value="loc.value">
                      {{ loc.label }}
                    </a-option>
                  </a-select>
                </a-col>
                <a-col :xs="24" :sm="8">
                  <a-input v-model="action.locator_value" size="small" placeholder="定位表达式" />
                </a-col>
                <a-col :xs="24" :sm="8">
                  <a-input v-model="action.selector" size="small" placeholder="原始 selector" />
                </a-col>
              </a-row>
            </div>
          </div>
          <a-empty v-else description="暂无可保存动作，请检查原始录制脚本或丢弃草稿" />
        </a-form>

        <a-collapse :default-active-key="['script']">
          <a-collapse-item key="preview" header="原始分段预览（保存时会按上方编辑内容重新生成）">
            <div
              v-for="step in currentSession.preview_payload?.page_steps || []"
              :key="`${step.index}-${step.name}`"
              class="preview-block"
            >
              <div class="preview-title">
                <strong>{{ step.name }}</strong>
                <span class="preview-meta">{{ step.page_name }}{{ step.url ? ` · ${step.url}` : '' }}</span>
              </div>
              <ol class="preview-actions">
                <li v-for="action in step.actions" :key="`${step.index}-${action.line_no}-${action.operation}`">
                  {{ action.description || action.operation }}
                </li>
              </ol>
            </div>
            <a-empty v-if="!(currentSession.preview_payload?.page_steps || []).length" description="暂无可预览的结构化动作" />
          </a-collapse-item>
          <a-collapse-item key="script" header="原始录制脚本">
            <pre class="script-preview">{{ currentSession.raw_script || '(无脚本输出)' }}</pre>
          </a-collapse-item>
          <a-collapse-item key="unsupported" header="未支持语句">
            <pre class="script-preview">{{ unsupportedLinesText }}</pre>
          </a-collapse-item>
        </a-collapse>
      </div>
    </template>

    <div class="footer-actions">
      <template v-if="phase === 'form'">
        <a-button @click="handleClose">取消</a-button>
        <a-button type="primary" :loading="submitting" :disabled="headlessSelected" @click="handleStartRecording">
          开始录制
        </a-button>
      </template>
      <template v-else-if="phase === 'recording'">
        <a-button @click="handleCancelRecording" :loading="stopping">取消录制</a-button>
        <a-button type="primary" :loading="stopping" @click="handleStopRecording(false)">
          停止录制并生成草稿
        </a-button>
      </template>
      <template v-else>
        <a-button @click="handleDiscardDraft" :loading="discarding">丢弃草稿</a-button>
        <a-button type="primary" :loading="saving" :disabled="editableActions.length === 0" @click="handleMaterialize">
          保存为正式数据
        </a-button>
      </template>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { actuatorApi, envConfigApi, moduleApi, pageApi, recordingApi, type ActuatorInfo } from '../api'
import type { UiEnvironmentConfig, UiModule, UiPage, UiRecordingAction, UiRecordingSession, UiRecordingTargetType } from '../types'
import { extractListData, extractResponseData } from '../types'
import { uiWebSocket, UiSocketEnum, type RecordingStatusResult, type SocketDataModel } from '../services/websocket'

const props = defineProps<{
  visible: boolean
  projectId?: number
  defaultModuleId?: number
  defaultTargetType: UiRecordingTargetType
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
}>()

const moduleOptions = ref<UiModule[]>([])
const pageOptions = ref<UiPage[]>([])
const envConfigs = ref<UiEnvironmentConfig[]>([])
const actuators = ref<ActuatorInfo[]>([])

const phase = ref<'form' | 'recording' | 'draft'>('form')
const submitting = ref(false)
const stopping = ref(false)
const saving = ref(false)
const discarding = ref(false)
const waitingForStart = ref(false)
const currentRecordingId = ref<number | null>(null)
const cancelRequested = ref(false)
const lastHandledResultId = ref<number | null>(null)
const currentSession = ref<UiRecordingSession | null>(null)
const draftName = ref('')
const editableActions = ref<Array<UiRecordingAction & { _key?: string }>>([])

const formData = reactive({
  target_type: props.defaultTargetType as UiRecordingTargetType,
  module: undefined as number | undefined,
  page: undefined as number | undefined,
  env_config_id: undefined as number | undefined,
  actuator_id: undefined as string | undefined,
  name: '',
})

const openActuators = computed(() => actuators.value.filter(act => act.is_open))
const headlessSelected = computed(() => {
  const selected = envConfigs.value.find(env => env.id === formData.env_config_id)
  return Boolean(selected?.headless)
})
const filteredPages = computed(() => {
  if (!formData.module) return pageOptions.value
  return pageOptions.value.filter(page => page.module === formData.module)
})
const modalTitle = computed(() => {
  if (phase.value === 'recording') return '录制中'
  if (phase.value === 'draft') return '录制草稿预览'
  return formData.target_type === 'test_case' ? '录制生成用例' : '录制生成步骤'
})
const selectedActuatorLabel = computed(() => {
  const actuator = actuators.value.find(act => act.id === formData.actuator_id)
  return actuator?.name || actuator?.id || '-'
})
const unsupportedLinesText = computed(() => {
  const lines = currentSession.value?.preview_payload?.unsupported_lines || []
  return lines.length ? lines.join('\n') : '(无未支持语句)'
})
const operationOptions = [
  { value: 'goto', label: '打开页面' },
  { value: 'fill', label: '输入' },
  { value: 'clear', label: '清空' },
  { value: 'click', label: '点击' },
  { value: 'dblclick', label: '双击' },
  { value: 'press', label: '按键' },
  { value: 'select', label: '选择' },
  { value: 'check', label: '勾选' },
  { value: 'uncheck', label: '取消勾选' },
  { value: 'hover', label: '悬浮' },
  { value: 'focus', label: '聚焦' },
  { value: 'assert_visible', label: '断言可见' },
  { value: 'assert_hidden', label: '断言隐藏' },
  { value: 'assert_contain_text', label: '断言包含文本' },
  { value: 'assert_text', label: '断言文本' },
  { value: 'assert_value', label: '断言值' },
  { value: 'assert_url', label: '断言URL' },
  { value: 'assert_title', label: '断言标题' },
]
const locatorTypeOptions = [
  { value: 'id', label: 'ID' },
  { value: 'name', label: 'Name' },
  { value: 'css', label: 'CSS' },
  { value: 'xpath', label: 'XPath' },
  { value: 'text', label: '文本' },
  { value: 'role', label: 'Role' },
  { value: 'label', label: 'Label' },
  { value: 'placeholder', label: 'Placeholder' },
  { value: 'test_id', label: 'Test ID' },
]

const flattenModules = (modules: UiModule[], level = 0, visited = new Set<number>()): UiModule[] => {
  const result: UiModule[] = []
  for (const mod of modules) {
    if (visited.has(mod.id)) continue
    visited.add(mod.id)
    result.push({ ...mod, name: '\u00A0\u00A0'.repeat(level) + mod.name })
    if (mod.children?.length) {
      result.push(...flattenModules(mod.children as UiModule[], level + 1, visited))
    }
  }
  return result
}

const resetState = () => {
  phase.value = 'form'
  submitting.value = false
  stopping.value = false
  saving.value = false
  discarding.value = false
  waitingForStart.value = false
  currentRecordingId.value = null
  cancelRequested.value = false
  currentSession.value = null
  draftName.value = ''
  editableActions.value = []
  formData.target_type = props.defaultTargetType
  formData.module = props.defaultModuleId
  formData.page = undefined
  formData.env_config_id = undefined
  formData.actuator_id = openActuators.value[0]?.id
  formData.name = props.defaultTargetType === 'test_case' ? '录制生成用例' : '录制生成步骤'
}

const syncDraftEditor = (session?: UiRecordingSession | null) => {
  draftName.value = session?.name || formData.name
  editableActions.value = (session?.normalized_actions || []).map((action, index) => ({
    ...action,
    _key: `${Date.now()}-${index}-${action.line_no || ''}`,
  }))
}

const loadOptions = async () => {
  if (!props.projectId) return
  const [moduleRes, pageRes, envRes, actuatorRes] = await Promise.all([
    moduleApi.tree(props.projectId),
    pageApi.list({ project: props.projectId }),
    envConfigApi.list({ project: props.projectId }),
    actuatorApi.list(),
  ])
  moduleOptions.value = flattenModules(extractResponseData<UiModule[]>(moduleRes) || [])
  pageOptions.value = extractListData<UiPage>(pageRes)
  envConfigs.value = extractListData<UiEnvironmentConfig>(envRes)
  actuators.value = extractResponseData<{ count: number; items: ActuatorInfo[] }>(actuatorRes)?.items || []
  if (!formData.actuator_id && openActuators.value.length) {
    formData.actuator_id = openActuators.value[0].id
  }
  // 自动选中执行环境:优先项目默认环境(is_default),否则取第一个,省去每次手动选
  if (!formData.env_config_id && envConfigs.value.length) {
    const defaultEnv = envConfigs.value.find(env => env.is_default)
    formData.env_config_id = (defaultEnv || envConfigs.value[0]).id
  }
}

const onRecordStatus = (socketData: SocketDataModel) => {
  const payload = socketData.data?.func_args as RecordingStatusResult | undefined
  if (!payload) return
  if (waitingForStart.value && payload.status === 'recording') {
    waitingForStart.value = false
    currentRecordingId.value = payload.recording_id
    currentSession.value = (payload.recording as UiRecordingSession) || null
    phase.value = 'recording'
    submitting.value = false
  }
}

const onRecordResult = (socketData: SocketDataModel) => {
  const payload = socketData.data?.func_args as { recording_id: number; status: string; recording?: UiRecordingSession } | undefined
  if (!payload) return
  if (currentRecordingId.value && payload.recording_id !== currentRecordingId.value) return
  // 去重:同一录制的结果只处理一次(避免执行器/后端重发导致重复 toast)
  if (lastHandledResultId.value === payload.recording_id) return
  lastHandledResultId.value = payload.recording_id
  waitingForStart.value = false
  stopping.value = false
  submitting.value = false
  currentRecordingId.value = payload.recording_id
  currentSession.value = payload.recording || null
  syncDraftEditor(payload.recording || null)
  // 用户主动取消,或后端标记 cancelled:统一按"已取消"处理,不弹"未提取到结构化数据"
  if (cancelRequested.value || payload.status === 'cancelled') {
    Message.info('录制已取消')
    emit('update:visible', false)
    resetState()
    return
  }
  phase.value = 'draft'
  if (payload.status === 'failed') {
    Message.warning(payload.recording?.error_message || '录制已结束，但未生成稳定草稿')
  } else {
    Message.success('录制草稿已生成')
  }
}

const offStatus = uiWebSocket.on(UiSocketEnum.RECORD_STATUS, onRecordStatus)
const offResult = uiWebSocket.on(UiSocketEnum.RECORD_RESULT, onRecordResult)

const ensureConnected = async () => {
  if (!uiWebSocket.connected.value) {
    await uiWebSocket.connect()
  }
}

const validateForm = () => {
  if (!props.projectId) {
    Message.error('当前未选择项目')
    return false
  }
  if (!formData.module || !formData.actuator_id || !formData.name.trim()) {
    Message.warning('请完善录制名称、模块和执行器')
    return false
  }
  return true
}

const handleStartRecording = async () => {
  if (!validateForm()) return
  submitting.value = true
  waitingForStart.value = true
  try {
    await ensureConnected()
    const sent = uiWebSocket.startRecording({
      project: props.projectId!,
      module: formData.module!,
      page: formData.target_type === 'page_step' ? formData.page : undefined,
      env_config_id: formData.env_config_id,
      actuator_id: formData.actuator_id,
      target_type: formData.target_type,
      name: formData.name.trim(),
    })
    if (!sent) {
      waitingForStart.value = false
      submitting.value = false
      Message.error('WebSocket 未连接，无法启动录制')
    }
  } catch (error) {
    waitingForStart.value = false
    submitting.value = false
    Message.error('启动录制失败')
    console.error(error)
  }
}

const handleStopRecording = async (cancel: boolean) => {
  if (!currentRecordingId.value) return
  stopping.value = true
  try {
    await ensureConnected()
    const sent = uiWebSocket.stopRecording(currentRecordingId.value, formData.actuator_id, cancel)
    if (!sent) {
      stopping.value = false
      Message.error('无法通知执行器停止录制')
    }
  } catch (error) {
    stopping.value = false
    Message.error('停止录制失败')
    console.error(error)
  }
}

const handleCancelRecording = () => {
  cancelRequested.value = true
  handleStopRecording(true)
}

const handleMaterialize = async () => {
  if (!currentRecordingId.value) return
  const actions = editableActions.value
    .map(({ _key, ...action }) => action)
    .filter(action => action.operation)
  if (!actions.length) {
    Message.warning('请至少保留一个可保存动作')
    return
  }
  saving.value = true
  try {
    const res = await recordingApi.materialize(currentRecordingId.value, {
      name: draftName.value.trim() || currentSession.value?.name,
      normalized_actions: actions,
    })
    const payload = extractResponseData<any>(res)
    const recording = payload?.recording as UiRecordingSession | undefined
    if (recording) currentSession.value = recording
    window.dispatchEvent(new CustomEvent('ui-automation-recording-materialized', {
      detail: {
        targetType: formData.target_type,
        recordingId: currentRecordingId.value,
        generatedPageStepIds: payload?.generated_page_step_ids || [],
        generatedTestCaseId: payload?.generated_test_case_id || null,
      }
    }))
    Message.success('录制内容已保存为正式数据')
    emit('update:visible', false)
    resetState()
  } catch (error) {
    Message.error('录制草稿保存失败')
    console.error(error)
  } finally {
    saving.value = false
  }
}

const addDraftAction = () => {
  editableActions.value.push({
    _key: `${Date.now()}-${Math.random()}`,
    line_no: editableActions.value.length + 1,
    operation: 'click',
    description: '',
    selector: '',
    locator_type: 'css',
    locator_value: '',
    value: '',
  })
}

const removeDraftAction = (index: number) => {
  editableActions.value.splice(index, 1)
}

const handleDiscardDraft = async () => {
  if (!currentRecordingId.value) {
    emit('update:visible', false)
    resetState()
    return
  }
  discarding.value = true
  try {
    await recordingApi.discard(currentRecordingId.value)
    Message.info('录制草稿已丢弃')
    emit('update:visible', false)
    resetState()
  } catch (error) {
    Message.error('丢弃录制草稿失败')
    console.error(error)
  } finally {
    discarding.value = false
  }
}

const handleClose = () => {
  if (phase.value === 'recording' && currentRecordingId.value) {
    Message.warning('录制进行中，请先停止或取消录制')
    return
  }
  emit('update:visible', false)
  resetState()
}

watch(() => props.visible, (val) => {
  if (val) {
    resetState()
    void loadOptions()
    return
  }
  resetState()
})

watch(() => props.defaultModuleId, (value) => {
  if (phase.value === 'form') {
    formData.module = value
  }
})

watch(() => props.defaultTargetType, (value) => {
  if (phase.value === 'form') {
    formData.target_type = value
  }
})

watch(() => formData.module, () => {
  if (formData.page && !filteredPages.value.some(page => page.id === formData.page)) {
    formData.page = undefined
  }
})

watch(() => formData.target_type, (value) => {
  if (phase.value !== 'form') return
  if (value !== 'page_step') {
    formData.page = undefined
  }
  if (!formData.name || formData.name === '录制生成用例' || formData.name === '录制生成步骤') {
    formData.name = value === 'test_case' ? '录制生成用例' : '录制生成步骤'
  }
})

onBeforeUnmount(() => {
  offStatus()
  offResult()
})
</script>

<style scoped lang="scss">
.footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

.preview-block {
  padding: 12px 0;
  border-bottom: 1px solid var(--color-border-2);
}

.draft-editor {
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid var(--color-border-2);
  border-radius: 8px;
  background: var(--color-fill-1);
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.editable-action-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.editable-action-card {
  padding: 12px;
  border: 1px solid var(--color-border-2);
  border-radius: 8px;
  background: var(--color-bg-2);
}

.action-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.operation-select {
  width: 150px;
}

.preview-block:last-child {
  border-bottom: none;
}

.preview-title {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.preview-meta {
  color: var(--color-text-3);
  font-size: 12px;
}

.preview-actions {
  margin: 0;
  padding-left: 18px;
}

.script-preview {
  margin: 0;
  padding: 12px;
  background: var(--color-fill-2);
  border-radius: 6px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
}
</style>
