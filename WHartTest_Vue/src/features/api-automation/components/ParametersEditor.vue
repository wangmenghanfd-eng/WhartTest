<template>
  <div class="parameters-editor">
    <div class="pe-head">
      <span class="pe-hint">数据驱动：每个参数一组取值，多参数取笛卡尔积逐组执行。</span>
      <a-radio-group v-model="mode" type="button" size="mini">
        <a-radio value="rows">表格</a-radio>
        <a-radio value="json">JSON</a-radio>
      </a-radio-group>
    </div>

    <template v-if="mode === 'rows'">
      <div v-if="!rows.length" class="empty-tip">暂无参数化（留空则用例只执行一次）</div>
      <div v-for="(row, idx) in rows" :key="idx" class="param-row">
        <a-input v-model="row.name" placeholder="参数名，如 ver" size="small" class="col-name" @input="emitFromRows" />
        <a-input
          v-model="row.valuesText"
          placeholder="取值列表，逗号分隔，如 v1, v2, v3"
          size="small"
          class="col-values"
          @input="emitFromRows"
        />
        <a-button type="text" status="danger" size="mini" @click="removeRow(idx)">删除</a-button>
      </div>
      <a-button size="small" type="outline" long class="add-btn" @click="addRow">+ 添加参数</a-button>
      <div class="pe-tip">复合参数（如 user-pwd 每组多个值）请切到 JSON 模式编辑。</div>
    </template>

    <template v-else>
      <a-textarea
        v-model="jsonText"
        :auto-size="{ minRows: 4, maxRows: 12 }"
        placeholder='{"ver": ["v1","v2"], "user-pwd": [["u1","p1"],["u2","p2"]]}'
        class="json-area"
        @blur="emitFromJson"
      />
      <div v-if="jsonError" class="json-error">JSON 解析失败：{{ jsonError }}</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

type ParamMap = Record<string, unknown>

const props = defineProps<{ modelValue?: ParamMap }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: ParamMap): void }>()

const mode = ref<'rows' | 'json'>('rows')
const rows = ref<{ name: string; valuesText: string }[]>([])
const jsonText = ref('{}')
const jsonError = ref('')
let lastEmitted = ''

function parseToken(token: string): unknown {
  const t = token.trim()
  if (t === '') return ''
  try {
    return JSON.parse(t)
  } catch {
    return t
  }
}

function toRows(obj: ParamMap): { name: string; valuesText: string }[] {
  return Object.entries(obj || {}).map(([name, val]) => {
    let valuesText = ''
    if (Array.isArray(val)) {
      valuesText = val
        .map((x) => (typeof x === 'object' && x !== null ? JSON.stringify(x) : String(x)))
        .join(', ')
    } else if (val !== undefined && val !== null) {
      valuesText = String(val)
    }
    return { name, valuesText }
  })
}

function buildFromRows(): ParamMap {
  const obj: ParamMap = {}
  for (const r of rows.value) {
    const name = r.name.trim()
    if (!name) continue
    const values = r.valuesText
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s !== '')
      .map(parseToken)
    obj[name] = values
  }
  return obj
}

function emitValue(obj: ParamMap) {
  lastEmitted = JSON.stringify(obj)
  emit('update:modelValue', obj)
}

function emitFromRows() {
  emitValue(buildFromRows())
}

function removeRow(idx: number) {
  rows.value.splice(idx, 1)
  emitFromRows()
}

function addRow() {
  rows.value.push({ name: '', valuesText: '' })
}

function emitFromJson() {
  const text = jsonText.value.trim()
  if (text === '') {
    jsonError.value = ''
    emitValue({})
    return
  }
  try {
    const parsed = JSON.parse(text)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      jsonError.value = '需为对象，如 {"ver": ["v1","v2"]}'
      return
    }
    jsonError.value = ''
    emitValue(parsed as ParamMap)
  } catch (e) {
    jsonError.value = String((e as Error).message || e)
  }
}

// 外部（如打开用例）载入 modelValue 时同步到编辑器
watch(
  () => props.modelValue,
  (val) => {
    const incoming = JSON.stringify(val || {})
    if (incoming === lastEmitted) return
    const obj = (val || {}) as ParamMap
    rows.value = toRows(obj)
    jsonText.value = Object.keys(obj).length ? JSON.stringify(obj, null, 2) : '{}'
    lastEmitted = incoming
  },
  { immediate: true },
)

// 切到 JSON 模式时用当前值刷新文本
watch(mode, (m) => {
  if (m === 'json') {
    const obj = buildFromRows()
    jsonText.value = Object.keys(obj).length ? JSON.stringify(obj, null, 2) : '{}'
  } else {
    rows.value = toRows((props.modelValue || {}) as ParamMap)
  }
})
</script>

<style scoped>
.parameters-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pe-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.pe-hint,
.pe-tip {
  color: var(--color-text-3);
  font-size: 12px;
}
.empty-tip {
  color: var(--color-text-3);
  font-size: 12px;
  padding: 4px 0;
}
.param-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.col-name {
  width: 160px;
  flex: 0 0 160px;
}
.col-values {
  flex: 1 1 240px;
  min-width: 160px;
}
.json-error {
  color: rgb(var(--red-6));
  font-size: 12px;
}
.add-btn {
  margin-top: 4px;
}
</style>
