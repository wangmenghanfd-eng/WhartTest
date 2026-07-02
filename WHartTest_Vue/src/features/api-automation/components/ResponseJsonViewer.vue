<template>
  <a-drawer
    :visible="visible"
    :width="480"
    title="从响应取值（点选生成 JMESPath 路径）"
    :footer="false"
    @cancel="$emit('update:visible', false)"
  >
    <div v-if="json === null || json === undefined" class="empty-tip">
      当前没有响应数据。请先在用例里点【调试】运行一次，再回来取值。
    </div>
    <div v-else class="json-tree">
      <div
        v-for="row in rows"
        :key="row.path"
        class="json-row"
        :style="{ paddingLeft: `${row.depth * 16}px` }"
      >
        <span
          v-if="row.isContainer"
          class="toggle"
          @click="toggle(row.path)"
        >{{ expanded.has(row.path) ? '▾' : '▸' }}</span>
        <span v-else class="toggle toggle-placeholder"></span>
        <span class="json-key">{{ row.keyLabel }}</span>
        <span class="json-preview" :class="'t-' + row.valueType">{{ row.preview }}</span>
        <a-button
          type="text"
          size="mini"
          class="pick-btn"
          @click="pick(row)"
        >选取</a-button>
      </div>
    </div>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{ visible: boolean; json?: unknown }>()
const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'select', path: string, value: unknown): void
}>()

interface Row {
  path: string
  keyLabel: string
  depth: number
  valueType: string
  preview: string
  isContainer: boolean
  value: unknown
}

const expanded = ref<Set<string>>(new Set())

// 每次打开或响应变化时，默认展开前两层，便于快速取值
watch(
  () => [props.visible, props.json],
  () => {
    if (!props.visible) return
    const next = new Set<string>()
    const seed = (node: unknown, path: string, depth: number) => {
      if (depth > 1 || node === null || typeof node !== 'object') return
      if (path) next.add(path)
      const entries = Array.isArray(node)
        ? node.map((v, i) => [`${path}[${i}]`, v] as const)
        : Object.entries(node as Record<string, unknown>).map(([k, v]) => [childPath(path, k), v] as const)
      entries.forEach(([p, v]) => seed(v, p, depth + 1))
    }
    // 顶层容器本身用空 path 作为根，标记为已展开
    if (props.json && typeof props.json === 'object') {
      next.add('')
      seed(props.json, '', 0)
    }
    expanded.value = next
  },
  { immediate: true },
)

function childPath(parent: string, key: string): string {
  const safe = /^[A-Za-z_][A-Za-z0-9_]*$/.test(key)
  const token = safe ? key : `"${key}"`
  if (!parent) return safe ? key : `"${key}"`
  return safe ? `${parent}.${key}` : `${parent}."${key}"`
}

function typeOf(value: unknown): string {
  if (value === null) return 'null'
  if (Array.isArray(value)) return 'array'
  return typeof value
}

function previewOf(value: unknown, type: string): string {
  if (type === 'array') return `Array(${(value as unknown[]).length})`
  if (type === 'object') return `Object{${Object.keys(value as object).length}}`
  if (type === 'string') return `"${value as string}"`
  if (type === 'null') return 'null'
  return String(value)
}

const rows = computed<Row[]>(() => {
  const out: Row[] = []
  const walk = (node: unknown, path: string, keyLabel: string, depth: number) => {
    const type = typeOf(node)
    const isContainer = type === 'object' || type === 'array'
    out.push({
      path,
      keyLabel,
      depth,
      valueType: type,
      preview: previewOf(node, type),
      isContainer,
      value: node,
    })
    if (isContainer && expanded.value.has(path)) {
      if (type === 'array') {
        ;(node as unknown[]).forEach((v, i) => walk(v, `${path}[${i}]`, `[${i}]`, depth + 1))
      } else {
        Object.entries(node as Record<string, unknown>).forEach(([k, v]) =>
          walk(v, childPath(path, k), k, depth + 1),
        )
      }
    }
  }
  const root = props.json
  if (root === null || root === undefined) return out
  if (typeof root === 'object') {
    if (Array.isArray(root)) {
      root.forEach((v, i) => walk(v, `[${i}]`, `[${i}]`, 0))
    } else {
      Object.entries(root as Record<string, unknown>).forEach(([k, v]) => walk(v, childPath('', k), k, 0))
    }
  } else {
    walk(root, '', '(值)', 0)
  }
  return out
})

function toggle(path: string) {
  const next = new Set(expanded.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  expanded.value = next
}

function pick(row: Row) {
  emit('select', row.path, row.value)
  emit('update:visible', false)
}
</script>

<style scoped>
.empty-tip {
  color: var(--color-text-3);
  font-size: 13px;
  padding: 16px 4px;
  line-height: 1.6;
}
.json-tree {
  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12.5px;
}
.json-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
  border-bottom: 1px solid var(--color-fill-1);
}
.json-row:hover {
  background: var(--color-fill-1);
}
.toggle {
  width: 14px;
  cursor: pointer;
  color: var(--color-text-3);
  user-select: none;
  text-align: center;
}
.toggle-placeholder {
  cursor: default;
}
.json-key {
  color: var(--color-text-1);
  font-weight: 600;
}
.json-preview {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-3);
}
.json-preview.t-string {
  color: rgb(var(--green-6));
}
.json-preview.t-number {
  color: rgb(var(--arcoblue-6));
}
.json-preview.t-boolean {
  color: rgb(var(--orange-6));
}
.pick-btn {
  flex: 0 0 auto;
}
</style>
