<template>
  <a-drawer
    v-model:visible="visibleProxy"
    title="AI 增强 - 用例补全建议"
    :width="640"
    :ok-text="hasSuggestion ? (applying ? '应用中...' : '应用建议到用例') : '关闭'"
    :ok-button-props="{ disabled: applying, loading: applying }"
    @ok="onApply"
    @cancel="handleCancel"
  >
    <div v-if="loading" class="state-block">
      <a-spin /><span style="margin-left: 8px">LLM 思考中...</span>
    </div>

    <a-alert
      v-else-if="applying"
      type="info"
      class="state-alert"
      content="正在应用 AI 建议并保存到当前用例，请稍候..."
    />

    <a-alert v-else-if="payload?.error" type="warning" :content="payload.error" />

    <template v-else-if="payload">
      <div class="content-wrap">
        <div v-if="applying" class="applying-overlay">
          <a-spin size="large" />
          <div class="applying-title">正在应用 AI 建议</div>
          <div class="applying-desc">正在保存到当前用例并刷新列表，请稍候...</div>
        </div>
        <a-descriptions :column="1" :data="meta" />

        <a-divider>AI 说明</a-divider>
        <a-textarea
          v-model="editRationale"
          :auto-size="{ minRows: 2, maxRows: 4 }"
          placeholder="可补充说明本次建议的用途"
        />

        <a-divider>建议新增的断言</a-divider>
        <AssertionEditor v-model="editAssertions" />

        <a-divider>建议新增的提取器</a-divider>
        <ExtractorEditor v-model="editExtractors" />
      </div>
    </template>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { apiCaseApi } from '../api'
import { unwrapData } from '../types'
import AssertionEditor from './AssertionEditor.vue'
import ExtractorEditor from './ExtractorEditor.vue'

const props = defineProps<{
  visible: boolean
  caseId: number | null
  caseName?: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'applied', payload: {
    assertions: number
    extractors: number
    toastId: string
    mergedAssertions: Array<Record<string, any>>
    mergedExtractors: Array<Record<string, any>>
  }): void
}>()

const visibleProxy = computed<boolean>({
  get: () => props.visible,
  set: (value) => emit('update:visible', value),
})

const loading = ref(false)
const applying = ref(false)
const payload = ref<any>(null)
const editAssertions = ref<Array<Record<string, any>>>([])
const editExtractors = ref<Array<Record<string, any>>>([])
const editRationale = ref('')
const requestSeq = ref(0)
const AI_ENHANCE_TOAST_ID = 'single-ai-enhance-preview'

const hasSuggestion = computed(() => {
  return editAssertions.value.length + editExtractors.value.length > 0
})

const meta = computed(() => {
  if (!payload.value) return []
  return [
    { label: '用例', value: props.caseName || `#${props.caseId}` },
    { label: '当前断言数', value: payload.value.current.assertions.length },
    { label: '当前提取器数', value: payload.value.current.extractors.length },
    { label: '建议新增断言', value: editAssertions.value.length },
    { label: '建议新增提取器', value: editExtractors.value.length },
  ]
})

function handleCancel() {
  const wasLoading = loading.value
  requestSeq.value += 1
  loading.value = false
  applying.value = false
  visibleProxy.value = false
  if (wasLoading) {
    Message.warning({
      id: AI_ENHANCE_TOAST_ID,
      content: '已取消当前 AI 增强预览，可重新打开后继续增强',
      duration: 1800,
    })
  }
}

async function load() {
  if (!props.caseId) return
  const currentSeq = ++requestSeq.value
  loading.value = true
  payload.value = null
  Message.loading({
    id: AI_ENHANCE_TOAST_ID,
    content: '正在生成当前用例的 AI 增强建议...',
    duration: 0,
  })
  try {
    const res = await apiCaseApi.aiEnhance(props.caseId, { apply: false })
    if (currentSeq !== requestSeq.value || !visibleProxy.value) return
    payload.value = unwrapData<any>(res)
    editAssertions.value = Array.isArray(payload.value?.suggested?.assertions)
      ? payload.value.suggested.assertions.map((it: Record<string, any>) => ({ ...it }))
      : []
    editExtractors.value = Array.isArray(payload.value?.suggested?.extractors)
      ? payload.value.suggested.extractors.map((it: Record<string, any>) => ({ ...it }))
      : []
    editRationale.value = String(payload.value?.rationale || '')
    Message.success({
      id: AI_ENHANCE_TOAST_ID,
      content: 'AI 增强建议已生成',
      duration: 1800,
    })
  } catch (err: any) {
    if (currentSeq !== requestSeq.value || !visibleProxy.value) return
    payload.value = { error: err?.error || err?.message || '调用失败' }
    Message.error({
      id: AI_ENHANCE_TOAST_ID,
      content: err?.error || err?.message || 'AI 增强预览失败',
      duration: 3000,
    })
  } finally {
    if (currentSeq === requestSeq.value) {
      loading.value = false
    }
  }
}

async function onApply() {
  if (!hasSuggestion.value || !props.caseId) {
    visibleProxy.value = false
    return
  }
  applying.value = true
  const toastId = `ai-enhance-${props.caseId}-${Date.now()}`
  Message.loading({ id: toastId, content: '正在应用 AI 建议并保存到当前用例，请稍候...', duration: 0 })
  try {
    const res = await apiCaseApi.aiEnhance(props.caseId, {
      apply: true,
      suggested: {
        assertions: editAssertions.value || [],
        extractors: editExtractors.value || [],
        rationale: editRationale.value || '',
      },
    })
    const data = unwrapData<any>(res)
    emit('applied', {
      assertions: data?.suggested?.assertions?.length || 0,
      extractors: data?.suggested?.extractors?.length || 0,
      toastId,
      mergedAssertions: Array.isArray(data?.merged?.assertions) ? data.merged.assertions : [],
      mergedExtractors: Array.isArray(data?.merged?.extractors) ? data.merged.extractors : [],
    })
    visibleProxy.value = false
  } catch (err: any) {
    Message.error({ id: toastId, content: err?.error || '应用失败', duration: 4000 })
  } finally {
    applying.value = false
  }
}

defineExpose({ load })

watch(
  () => props.visible,
  (visible) => {
    if (!visible) {
      requestSeq.value += 1
      loading.value = false
      applying.value = false
    }
  },
)
</script>

<style scoped>
.state-block {
  display: flex;
  align-items: center;
  padding: 32px 0;
  justify-content: center;
}
.rationale {
  color: var(--color-text-2);
  white-space: pre-wrap;
}
.state-alert {
  margin-bottom: 12px;
}
.content-wrap {
  position: relative;
}
.applying-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: color-mix(in srgb, var(--color-bg-2) 90%, transparent);
  backdrop-filter: blur(2px);
  border-radius: 8px;
  text-align: center;
}
.applying-title {
  color: var(--color-text-1);
  font-weight: 600;
}
.applying-desc {
  color: var(--color-text-3);
  font-size: 12px;
}
</style>
