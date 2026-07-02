<template>
  <div class="kv-editor">
    <div v-if="!rows.length" class="empty-tip">{{ emptyText }}</div>
    <div v-for="(row, idx) in rows" :key="idx" class="kv-row">
      <a-input v-model="row.key" :placeholder="keyPlaceholder" size="small" class="col-key" @input="emitValue" />
      <span class="sep">:</span>
      <a-input v-model="row.value" :placeholder="valuePlaceholder" size="small" class="col-value" @input="emitValue" />
      <a-button type="text" status="danger" size="mini" @click="removeRow(idx)">删除</a-button>
    </div>
    <a-button size="small" type="outline" long class="add-btn" @click="addRow">+ 添加</a-button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

type KVMap = Record<string, string>

const props = withDefaults(
  defineProps<{
    modelValue?: KVMap
    emptyText?: string
    keyPlaceholder?: string
    valuePlaceholder?: string
  }>(),
  {
    modelValue: () => ({}),
    emptyText: '暂无（点下方添加）',
    keyPlaceholder: '键',
    valuePlaceholder: '值',
  },
)
const emit = defineEmits<{ (e: 'update:modelValue', value: KVMap): void }>()

const rows = ref<{ key: string; value: string }[]>([])
let lastEmitted = ''

function toRows(obj: KVMap): { key: string; value: string }[] {
  return Object.entries(obj || {}).map(([key, value]) => ({ key, value: value == null ? '' : String(value) }))
}

function buildObject(): KVMap {
  const obj: KVMap = {}
  for (const r of rows.value) {
    const k = r.key.trim()
    if (!k) continue
    obj[k] = r.value
  }
  return obj
}

function emitValue() {
  const obj = buildObject()
  lastEmitted = JSON.stringify(obj)
  emit('update:modelValue', obj)
}

function addRow() {
  rows.value.push({ key: '', value: '' })
}

function removeRow(idx: number) {
  rows.value.splice(idx, 1)
  emitValue()
}

// 外部载入（如打开用例）时同步；避免自身 emit 触发的回环
watch(
  () => props.modelValue,
  (val) => {
    const incoming = JSON.stringify(val || {})
    if (incoming === lastEmitted) return
    rows.value = toRows(val || {})
    lastEmitted = incoming
  },
  { immediate: true },
)
</script>

<style scoped>
.kv-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.empty-tip {
  color: var(--color-text-3);
  font-size: 12px;
  padding: 4px 0;
}
.kv-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.col-key {
  width: 220px;
  flex: 0 0 220px;
}
.sep {
  color: var(--color-text-3);
}
.col-value {
  flex: 1 1 240px;
  min-width: 140px;
}
.add-btn {
  margin-top: 4px;
}
</style>
