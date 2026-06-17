<template>
  <a-modal v-model:visible="visible" title="选择接口用例" :width="700" :mask-closable="false" @cancel="handleCancel">
    <template #footer>
      <a-space>
        <span class="selected-count">已选 {{ selectedKeys.length }} 个用例</span>
        <a-button @click="handleCancel">取消</a-button>
        <a-button type="primary" @click="handleConfirm" :disabled="selectedKeys.length === 0">确定</a-button>
      </a-space>
    </template>

    <div class="filter-row">
      <a-input-search
        v-model="searchText"
        placeholder="搜索接口用例名称"
        allow-clear
        style="width: 220px"
        @search="loadData"
        @clear="loadData"
      />
      <a-select
        v-model="moduleFilter"
        placeholder="筛选模块"
        allow-clear
        style="width: 160px"
        @change="loadData"
      >
        <a-option v-for="m in modules" :key="m.id" :value="m.id">{{ m.name }}</a-option>
      </a-select>
    </div>

    <a-table
      :columns="columns"
      :data="testCases"
      :loading="loading"
      :pagination="pagination"
      :row-selection="{ type: 'checkbox', showCheckedAll: true }"
      v-model:selectedKeys="selectedKeys"
      row-key="id"
      size="small"
      @page-change="onPageChange"
    >
      <template #method="{ record }">
        <a-tag size="small" color="arcoblue">{{ record.method }}</a-tag>
      </template>
      <template #status="{ record }">
        <a-tag size="small" :color="record.status === 2 ? 'green' : record.status === 3 ? 'red' : 'gray'">
          {{ statusMap[record.status] || '未执行' }}
        </a-tag>
      </template>
    </a-table>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { apiCaseApi, apiModuleApi } from '@/features/api-automation/api'

const props = defineProps<{ projectId: number }>()
const emit = defineEmits<{ (e: 'confirm', ids: number[]): void }>()

const visible = ref(false)
const loading = ref(false)
const testCases = ref<any[]>([])
const modules = ref<{ id: number; name: string }[]>([])
const selectedKeys = ref<number[]>([])
const searchText = ref('')
const moduleFilter = ref<number | undefined>(undefined)
const pagination = reactive({ current: 1, pageSize: 10, total: 0, showTotal: true })
let searchTimer: number | undefined
const statusMap: Record<number, string> = { 0: '未执行', 1: '执行中', 2: '成功', 3: '失败' }

const columns = [
  { title: '用例名称', dataIndex: 'name', ellipsis: true },
  { title: '方法', slotName: 'method', width: 90 },
  { title: '路径', dataIndex: 'path', ellipsis: true },
  { title: '状态', slotName: 'status', width: 90 },
]

const loadData = async () => {
  loading.value = true
  try {
    const res = await apiCaseApi.list({
      project: props.projectId,
      search: searchText.value || undefined,
      module: moduleFilter.value,
      page: pagination.current as any,
      page_size: pagination.pageSize as any,
    } as any)
    const data = (res as any).data?.data
    if (data?.results) {
      testCases.value = data.results
      pagination.total = data.count || 0
    } else if (Array.isArray(data)) {
      testCases.value = data
      pagination.total = data.length
    }
  } catch {
    testCases.value = []
  } finally {
    loading.value = false
  }
}

const loadModules = async () => {
  try {
    const res = await apiModuleApi.list({ project: props.projectId })
    const data = (res as any).data?.data
    const list = data?.results || (Array.isArray(data) ? data : [])
    modules.value = list.map((m: any) => ({ id: m.id, name: m.name }))
  } catch {
    modules.value = []
  }
}

const onPageChange = (page: number) => {
  pagination.current = page
  loadData()
}

watch(searchText, () => {
  pagination.current = 1
  if (searchTimer) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    loadData()
  }, 250)
})

watch(moduleFilter, () => {
  pagination.current = 1
  loadData()
})

const handleCancel = () => {
  visible.value = false
}

const handleConfirm = () => {
  emit('confirm', [...selectedKeys.value])
  visible.value = false
}

const open = (preSelectedIds?: number[]) => {
  selectedKeys.value = preSelectedIds ? [...preSelectedIds] : []
  pagination.current = 1
  searchText.value = ''
  moduleFilter.value = undefined
  visible.value = true
  loadData()
  loadModules()
}

defineExpose({ open })
</script>

<style scoped>
.filter-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.selected-count {
  color: var(--color-text-3);
  font-size: 13px;
  margin-right: 8px;
}
</style>
