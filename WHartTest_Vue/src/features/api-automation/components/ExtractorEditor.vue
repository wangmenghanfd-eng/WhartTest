<template>
  <div class="extractor-editor">
    <div class="helper-tip">
      变量提取会把响应中的值保存成变量。最后一个输入框填写提取路径或表达式，例如 JSON 路径 `data.token`、响应头名或正则。
    </div>
    <div v-if="!items.length" class="empty-tip">
      暂无变量提取（执行后会把结果写入执行记录的 response_data.extracted）
    </div>
    <div v-for="(item, idx) in items" :key="idx" class="extractor-row">
      <a-input
        v-model="item.name"
        placeholder="变量名"
        size="small"
        class="col-name"
      />
      <a-select
        v-model="item.source"
        :options="SOURCE_OPTIONS"
        size="small"
        class="col-source"
      />
      <a-input
        v-model="item.path"
        :placeholder="pathPlaceholder(item.source)"
        size="small"
        class="col-path"
      />
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
      + 添加变量提取
    </a-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type Extractor = Record<string, any>

const props = defineProps<{ modelValue?: Extractor[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: Extractor[]): void }>()

const items = computed<Extractor[]>({
  get: () => props.modelValue ?? [],
  set: (value) => emit('update:modelValue', value),
})

const SOURCE_OPTIONS = [
  { label: 'JSON 字段', value: 'json_path' },
  { label: '响应头', value: 'header' },
  { label: '正则匹配', value: 'regex' },
]

function pathPlaceholder(source: string) {
  if (source === 'header') return '响应头名（如 X-Request-Id）'
  if (source === 'regex') return '正则表达式（首个分组为提取值）'
  return '如 data.token / items[0].id'
}

function add() {
  items.value = [...items.value, { name: '', source: 'json_path', path: '' }]
}

function remove(idx: number) {
  const next = [...items.value]
  next.splice(idx, 1)
  items.value = next
}
</script>

<style scoped>
.extractor-editor {
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
.extractor-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.col-name {
  width: 140px;
  flex: 0 0 140px;
}
.col-source {
  width: 110px;
  flex: 0 0 110px;
}
.col-path {
  flex: 1 1 200px;
  min-width: 140px;
}
.add-btn {
  margin-top: 4px;
}
</style>
