<template>
  <a-drawer
    v-model:visible="visibleProxy"
    title="AI 增强 - 用例补全建议"
    :width="640"
    :ok-text="hasSuggestion ? '应用建议到用例' : '关闭'"
    :ok-button-props="{ disabled: !hasSuggestion, loading: applying }"
    @ok="onApply"
    @cancel="visibleProxy = false"
  >
    <div v-if="loading" class="state-block">
      <a-spin /><span style="margin-left: 8px">LLM 思考中...</span>
    </div>

    <a-alert v-else-if="payload?.error" type="warning" :content="payload.error" />

    <template v-else-if="payload">
      <a-descriptions :column="1" :data="meta" />

      <a-divider>LLM 解释</a-divider>
      <p class="rationale">{{ payload.rationale || '（LLM 没有给出解释）' }}</p>

      <a-divider>建议新增的断言</a-divider>
      <a-empty v-if="!payload.suggested.assertions.length" description="无新增" />
      <a-table
        v-else
        :data="payload.suggested.assertions"
        :columns="assertionColumns"
        :pagination="false"
        size="small"
      />

      <a-divider>建议新增的提取器</a-divider>
      <a-empty v-if="!payload.suggested.extractors.length" description="无新增" />
      <a-table
        v-else
        :data="payload.suggested.extractors"
        :columns="extractorColumns"
        :pagination="false"
        size="small"
      />
    </template>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { apiCaseApi } from '../api'
import { unwrapData } from '../types'

const props = defineProps<{
  visible: boolean
  caseId: number | null
  caseName?: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'applied'): void
}>()

const visibleProxy = computed<boolean>({
  get: () => props.visible,
  set: (value) => emit('update:visible', value),
})

const loading = ref(false)
const applying = ref(false)
const payload = ref<any>(null)

const hasSuggestion = computed(() => {
  if (!payload.value) return false
  const s = payload.value.suggested
  return (s?.assertions?.length || 0) + (s?.extractors?.length || 0) > 0
})

const meta = computed(() => {
  if (!payload.value) return []
  return [
    { label: '用例', value: props.caseName || `#${props.caseId}` },
    { label: '当前断言数', value: payload.value.current.assertions.length },
    { label: '当前提取器数', value: payload.value.current.extractors.length },
    { label: '建议新增断言', value: payload.value.suggested.assertions.length },
    { label: '建议新增提取器', value: payload.value.suggested.extractors.length },
  ]
})

const assertionColumns = [
  { title: '类型', dataIndex: 'type', width: 110 },
  { title: '操作符', dataIndex: 'operator', width: 90 },
  { title: '目标', dataIndex: 'target' },
  { title: '期望', dataIndex: 'expected' },
]
const extractorColumns = [
  { title: '变量名', dataIndex: 'name', width: 140 },
  { title: '来源', dataIndex: 'source', width: 110 },
  { title: '表达式', dataIndex: 'expression' },
]

async function load() {
  if (!props.caseId) return
  loading.value = true
  payload.value = null
  try {
    const res = await apiCaseApi.aiEnhance(props.caseId, { apply: false })
    payload.value = unwrapData<any>(res)
  } catch (err: any) {
    payload.value = { error: err?.error || err?.message || '调用失败' }
  } finally {
    loading.value = false
  }
}

async function onApply(done: ((closed: boolean) => void) | undefined) {
  if (!hasSuggestion.value || !props.caseId) {
    visibleProxy.value = false
    if (done) done(true)
    return
  }
  applying.value = true
  try {
    const res = await apiCaseApi.aiEnhance(props.caseId, { apply: true })
    const data = unwrapData<any>(res)
    Message.success(`已合并 ${data?.suggested?.assertions?.length || 0} 条断言、${data?.suggested?.extractors?.length || 0} 条提取器`)
    emit('applied')
    visibleProxy.value = false
    if (done) done(true)
  } catch (err: any) {
    Message.error(err?.error || '应用失败')
    if (done) done(false)
  } finally {
    applying.value = false
  }
}

defineExpose({ load })
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
</style>
