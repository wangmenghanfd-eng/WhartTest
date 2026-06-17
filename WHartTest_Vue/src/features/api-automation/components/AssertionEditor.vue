<template>
  <div class="assertion-editor">
    <div class="helper-tip">
      断言用于校验接口响应是否符合预期；变量提取则是把响应值保存给后续步骤复用，两者不需要一一对应。
    </div>
    <div v-if="!items.length" class="empty-tip">暂无断言（执行时默认要求 status &lt; 500）</div>
    <div v-for="(item, idx) in items" :key="idx" class="assertion-row">
      <a-select
        v-model="item.type"
        :options="TYPE_OPTIONS"
        placeholder="断言类型"
        size="small"
        class="col-type"
        @change="onTypeChange(idx)"
      />
      <a-input
        v-if="needsPath(item.type)"
        v-model="item.path"
        :placeholder="pathPlaceholder(item.type)"
        size="small"
        class="col-path"
      />
      <a-select
        v-if="needsOperator(item.type)"
        v-model="item.operator"
        :options="operatorOptions(item.type)"
        size="small"
        class="col-op"
      />
      <a-input
        v-if="needsExpected(item.type, item.operator)"
        :model-value="expectedInputValue(item)"
        @update:model-value="updateExpected(idx, $event)"
        :placeholder="expectedPlaceholder(item.type)"
        size="small"
        class="col-expected"
      />
      <span
        v-else-if="showDisabledExpected(item.type, item.operator)"
        class="col-expected col-expected-disabled"
      >
        —
      </span>
      <a-button
        type="text"
        status="danger"
        size="mini"
        @click="remove(idx)"
      >
        删除
      </a-button>
    </div>
    <a-button size="small" type="outline" long class="add-btn" @click="add">
      + 添加断言
    </a-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type Assertion = Record<string, any>

const props = defineProps<{ modelValue?: Assertion[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: Assertion[]): void }>()

const items = computed<Assertion[]>({
  get: () => (props.modelValue ?? []).map((raw) => {
    const item = { ...raw }
    if (item.type === 'header_exists') {
      item.path = item.path || item.target || item.expected || ''
      item.target = item.path
      delete item.expected
    }
    if (item.type === 'json_path_length') {
      item.path = item.path || item.target || ''
      item.target = item.path
    }
    return item
  }),
  set: (value) => emit('update:modelValue', value.map((raw) => {
    const item = { ...raw }
    if (item.type === 'header_exists') {
      item.target = item.path || item.target || ''
      delete item.expected
    }
    if (item.type === 'json_path_length') {
      item.target = item.path || item.target || ''
    }
    return item
  })),
})

const TYPE_OPTIONS = [
  { label: '状态码', value: 'status_code' },
  { label: 'JSON 字段值', value: 'json_path' },
  { label: 'JSON 字段长度', value: 'json_path_length' },
  { label: 'JSON 字段类型', value: 'json_path_type' },
  { label: '响应体包含', value: 'body_contains' },
  { label: '响应体不包含', value: 'body_not_contains' },
  { label: '响应头存在', value: 'header_exists' },
  { label: '响应头值', value: 'header_value' },
]

const STATUS_CODE_OPS = [
  { label: '=', value: 'eq' },
  { label: '<', value: 'lt' },
  { label: 'in [..]', value: 'in' },
]

const COMMON_OPS = [
  { label: '=', value: 'eq' },
  { label: '!=', value: 'neq' },
  { label: '包含', value: 'contains' },
  { label: '不包含', value: 'not_contains' },
  { label: '正则', value: 'regex' },
  { label: '<', value: 'lt' },
  { label: '<=', value: 'lte' },
  { label: '>', value: 'gt' },
  { label: '>=', value: 'gte' },
  { label: '为空', value: 'is_empty' },
  { label: '不为空', value: 'is_not_empty' },
]

function needsOperator(type: string) {
  return type === 'status_code' || type === 'json_path' || type === 'json_path_length' || type === 'json_path_type' || type === 'header_value'
}

function needsPath(type: string) {
  return type === 'json_path' || type === 'json_path_length' || type === 'json_path_type' || type === 'header_value' || type === 'header_exists'
}

function needsExpected(type: string, operator?: string) {
  if (!type) return true
  if (type === 'header_exists') return false
  if (type === 'body_contains' || type === 'body_not_contains') return true
  if (type === 'status_code') return true
  // json_path / header_value: is_empty / is_not_empty 不需要 expected
  if (operator === 'is_empty' || operator === 'is_not_empty') return false
  return true
}

function showDisabledExpected(type: string, operator?: string) {
  if (type === 'header_exists') return false
  return !needsExpected(type, operator)
}

function operatorOptions(type: string) {
  return type === 'status_code' ? STATUS_CODE_OPS : COMMON_OPS
}

function pathPlaceholder(type: string) {
  if (type === 'json_path') return '如 data.token / items[0].id'
  if (type === 'json_path_length') return '如 items / data.list / items[0].tags'
  if (type === 'json_path_type') return '如 data.token / items[0].id'
  if (type === 'header_exists') return '响应头名（如 X-Trace-Id）'
  if (type === 'header_value') return '响应头名（如 X-Total）'
  return ''
}

function expectedPlaceholder(type: string) {
  if (type === 'status_code') return '如 200 或 200,201'
  if (type === 'json_path_length') return '如 1 / 0 / 10'
  if (type === 'body_contains' || type === 'body_not_contains') return '响应体子串'
  if (type === 'json_path_type') return 'string / number / boolean / object / array / null'
  return '期望值'
}

function expectedInputValue(item: Assertion) {
  if (item?.expected === null || item?.expected === undefined) return 'null'
  return String(item.expected)
}

function updateExpected(idx: number, value: string) {
  const next = [...items.value]
  const item = { ...next[idx] }
  item.expected = value
  next[idx] = item
  items.value = next
}

function add() {
  items.value = [...items.value, { type: 'status_code', operator: 'eq', expected: 200 }]
}

function remove(idx: number) {
  const next = [...items.value]
  next.splice(idx, 1)
  items.value = next
}

function onTypeChange(idx: number) {
  const item = { ...items.value[idx] }
  // 调整默认 operator
  if (item.type === 'status_code') {
    item.operator = item.operator && ['eq', 'lt', 'in'].includes(item.operator) ? item.operator : 'eq'
  } else if (item.type === 'json_path_length') {
    item.operator = item.operator || 'eq'
  } else if (needsOperator(item.type)) {
    item.operator = item.operator || 'eq'
  } else {
    delete item.operator
  }
  if (!needsPath(item.type)) {
    delete item.path
  } else if (!item.path && item.target) {
    item.path = item.target
  }
  if (item.type === 'header_exists') {
    item.target = item.path || item.target || ''
    delete item.expected
  }
  const next = [...items.value]
  next[idx] = item
  items.value = next
}
</script>

<style scoped>
.assertion-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.helper-tip {
  color: var(--color-text-3);
  font-size: 12px;
  line-height: 1.5;
}
.empty-tip {
  color: var(--color-text-3);
  font-size: 12px;
  padding: 4px 0;
}
.assertion-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.col-type {
  width: 130px;
  flex: 0 0 130px;
}
.col-path {
  width: 160px;
  flex: 1 1 160px;
  min-width: 100px;
}
.col-op {
  width: 100px;
  flex: 0 0 100px;
}
.col-expected {
  flex: 1 1 140px;
  min-width: 100px;
}
.col-expected-disabled {
  color: var(--color-text-3);
  text-align: center;
  font-size: 12px;
}
.add-btn {
  margin-top: 4px;
}
</style>
