<template>
  <div class="functions-panel">
    <div class="toolbar">
      <a-input-search
        v-model="search"
        placeholder="搜索函数名/描述"
        allow-clear
        style="width: 260px"
        @search="fetchList"
        @clear="fetchList"
      />
      <a-button type="primary" @click="openModal()">新增函数</a-button>
    </div>

    <a-alert class="tip" type="normal">
      <span v-pre>函数体用 def 定义；用例任意字段里写 ${{ 函数名(参数) }} 即可调用（如 ${{ sign($ts) }}）。参数支持字面量、$变量 或 ${{ 变量 }}。</span>
    </a-alert>

    <a-table
      :data="list"
      :loading="loading"
      :pagination="false"
      row-key="id"
      size="small"
    >
      <template #columns>
        <a-table-column title="函数名" data-index="name" :width="180" />
        <a-table-column title="描述" data-index="description" ellipsis tooltip />
        <a-table-column title="启用" :width="90">
          <template #cell="{ record }">
            <a-tag :color="record.is_active ? 'green' : 'gray'">{{ record.is_active ? '启用' : '停用' }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="操作" :width="140">
          <template #cell="{ record }">
            <a-button type="text" size="mini" @click="openModal(record)">编辑</a-button>
            <a-button type="text" size="mini" status="danger" @click="remove(record)">删除</a-button>
          </template>
        </a-table-column>
      </template>
    </a-table>

    <a-modal
      v-model:visible="modalVisible"
      :title="editingId ? '编辑自定义函数' : '新增自定义函数'"
      :width="720"
      :ok-loading="submitting"
      @before-ok="submit"
    >
      <a-form :model="form" layout="vertical">
        <a-form-item label="函数名（调用名）" required>
          <a-input v-model="form.name" placeholder="如 sign / gen_ts" />
        </a-form-item>
        <a-form-item label="描述">
          <a-input v-model="form.description" placeholder="可选" />
        </a-form-item>
        <a-form-item label="启用">
          <a-switch v-model="form.is_active" />
        </a-form-item>
        <a-form-item label="Python 代码" required>
          <a-textarea
            v-model="form.code"
            :auto-size="{ minRows: 8, maxRows: 20 }"
            class="code-area"
            placeholder="import hashlib&#10;def sign(ts):&#10;    return hashlib.md5(str(ts).encode()).hexdigest()"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { apiCustomFunctionApi } from '../api'
import { unwrapPage } from '../types'
import type { ApiCustomFunction } from '../types'

const props = defineProps<{ projectId?: number }>()

const list = ref<ApiCustomFunction[]>([])
const loading = ref(false)
const search = ref('')

const modalVisible = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({ name: '', description: '', is_active: true, code: '' })

async function fetchList() {
  if (!props.projectId) return
  loading.value = true
  try {
    const res = await apiCustomFunctionApi.list({
      project: props.projectId,
      search: search.value || undefined,
      page_size: 200,
    })
    list.value = unwrapPage<ApiCustomFunction>(res).items
  } finally {
    loading.value = false
  }
}

function openModal(record?: ApiCustomFunction) {
  if (record) {
    editingId.value = record.id
    Object.assign(form, {
      name: record.name,
      description: record.description || '',
      is_active: record.is_active,
      code: record.code || '',
    })
  } else {
    editingId.value = null
    Object.assign(form, { name: '', description: '', is_active: true, code: '' })
  }
  modalVisible.value = true
}

async function submit(done: (closed: boolean) => void) {
  if (!props.projectId || !form.name.trim() || !form.code.trim()) {
    Message.warning('函数名和代码不能为空')
    done(false)
    return
  }
  submitting.value = true
  try {
    const payload = {
      project: props.projectId,
      name: form.name.trim(),
      description: form.description,
      is_active: form.is_active,
      code: form.code,
    }
    if (editingId.value) {
      await apiCustomFunctionApi.update(editingId.value, payload)
    } else {
      await apiCustomFunctionApi.create(payload)
    }
    Message.success('已保存')
    done(true)
    fetchList()
  } catch (e: any) {
    Message.error(e?.response?.data?.message || '保存失败')
    done(false)
  } finally {
    submitting.value = false
  }
}

function remove(record: ApiCustomFunction) {
  Modal.warning({
    title: '删除自定义函数',
    content: `确认删除函数「${record.name}」？`,
    hideCancel: false,
    onOk: async () => {
      await apiCustomFunctionApi.delete(record.id)
      Message.success('已删除')
      fetchList()
    },
  })
}

watch(() => props.projectId, fetchList, { immediate: true })
</script>

<style scoped>
.functions-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.tip {
  font-size: 12px;
}
.code-area {
  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
}
</style>
