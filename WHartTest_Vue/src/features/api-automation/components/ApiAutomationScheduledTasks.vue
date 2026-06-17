<template>
  <div class="scheduled-wrap">
    <a-alert closable style="margin-bottom: 12px;">
      这里展示的是「任务中心」里归属为“接口自动化”的定时任务，方便你在接口自动化页面直接查看和管理。若要新建任务，请前往「任务中心」。
    </a-alert>

    <a-spin :loading="loading">
      <a-empty v-if="!tasks.length" description="该项目暂无接口自动化定时任务。可前往任务中心创建。" />
      <a-table v-else :data="tasks" :columns="columns" :pagination="false" size="small">
        <template #status="{ record }">
          <a-tag :color="record.status === 'running' ? 'green' : record.status === 'executing' ? 'arcoblue' : 'gray'">
            {{ statusLabel(record.status) }}
          </a-tag>
        </template>
        <template #schedule="{ record }">
          <span>{{ record.schedule_display || record.schedule_type }}</span>
        </template>
        <template #lastRun="{ record }">
          <span>{{ formatTime(record.last_run_at) }}</span>
        </template>
        <template #cases="{ record }">
          <a-tag>{{ (record.api_testcase_ids || []).length }} 条用例</a-tag>
        </template>
        <template #ops="{ record }">
          <a-space size="mini">
            <a-button type="text" size="mini" @click="handleRunNow(record)">立即执行</a-button>
            <a-button v-if="record.status === 'disabled'" type="text" size="mini" @click="handleEnable(record)">启用</a-button>
            <a-button v-else type="text" size="mini" status="warning" @click="handleDisable(record)">禁用</a-button>
            <a-popconfirm content="确认删除该定时任务？" @ok="handleDelete(record)">
              <a-button type="text" size="mini" status="danger">删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </a-table>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import {
  deleteTask,
  disableTask,
  enableTask,
  getTaskList,
  runTaskNow,
  type ScheduledTask,
} from '@/features/task-center/services/taskService'

const props = defineProps<{ projectId: number | undefined; reloadKey?: number }>()

const loading = ref(false)
const tasks = ref<ScheduledTask[]>([])

const columns = [
  { title: 'ID', dataIndex: 'id', width: 60 },
  { title: '名称', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '调度', slotName: 'schedule', width: 160 },
  { title: '状态', slotName: 'status', width: 100 },
  { title: '用例', slotName: 'cases', width: 100 },
  { title: '上次运行', slotName: 'lastRun', width: 160 },
  { title: '操作', slotName: 'ops', width: 220, fixed: 'right' as const },
]

function statusLabel(s: string) {
  if (s === 'running') return '运行中'
  if (s === 'executing') return '执行中'
  return '未启用'
}

function formatTime(t: string | null) {
  if (!t) return '-'
  const d = new Date(t)
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  if (!props.projectId) return
  loading.value = true
  try {
    const page = await getTaskList(props.projectId, { module: 'api_automation' })
    tasks.value = page.results || []
  } catch (err: any) {
    Message.error(err?.message || '加载定时任务失败')
  } finally {
    loading.value = false
  }
}

async function handleRunNow(task: ScheduledTask) {
  if (!props.projectId) return
  try {
    const res = await runTaskNow(props.projectId, task.id)
    Message.success(res?.message || '已触发执行')
  } catch (err: any) {
    Message.error(err?.message || '触发失败')
  }
}

async function handleEnable(task: ScheduledTask) {
  if (!props.projectId) return
  try {
    await enableTask(props.projectId, task.id)
    Message.success('已启用')
    load()
  } catch (err: any) {
    Message.error(err?.message || '启用失败')
  }
}

async function handleDisable(task: ScheduledTask) {
  if (!props.projectId) return
  try {
    await disableTask(props.projectId, task.id)
    Message.success('已禁用')
    load()
  } catch (err: any) {
    Message.error(err?.message || '禁用失败')
  }
}

async function handleDelete(task: ScheduledTask) {
  if (!props.projectId) return
  try {
    await deleteTask(props.projectId, task.id)
    Message.success('已删除')
    load()
  } catch (err: any) {
    Message.error(err?.message || '删除失败')
  }
}

watch(() => [props.projectId, props.reloadKey], load, { immediate: true })
</script>

<style scoped>
.scheduled-wrap { padding: 4px 0 24px; }
</style>
