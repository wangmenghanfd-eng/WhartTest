<template>
  <div class="reports-wrap">
    <a-spin :loading="loading">
      <!-- 总览卡片 -->
      <a-grid :cols="4" :col-gap="16" :row-gap="16">
        <a-grid-item>
          <a-card hoverable>
            <a-statistic title="累计执行" :value="summary.total" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card hoverable>
            <a-statistic title="通过" :value="summary.passed" :value-style="{ color: 'rgb(var(--green-6))' }" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card hoverable>
            <a-statistic title="失败" :value="summary.failed" :value-style="{ color: 'rgb(var(--red-6))' }" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card hoverable>
            <a-statistic title="成功率" :value="summary.passRate" suffix="%" :precision="1" />
          </a-card>
        </a-grid-item>
      </a-grid>

      <a-divider>近 7 天趋势</a-divider>
      <div v-if="!trend.length" class="empty">最近 7 天没有执行记录</div>
      <div v-else class="trend-chart">
        <div v-for="d in trend" :key="d.date" class="trend-col">
          <div class="bars">
            <div class="bar passed" :style="{ height: barHeight(d.passed) + 'px' }" :title="`通过 ${d.passed}`"></div>
            <div class="bar failed" :style="{ height: barHeight(d.failed) + 'px' }" :title="`失败 ${d.failed}`"></div>
          </div>
          <div class="date">{{ d.date.slice(5) }}</div>
        </div>
      </div>

      <a-divider>按接口聚合（执行次数 Top 10）</a-divider>
      <a-table
        :data="byCase"
        :columns="byCaseColumns"
        :pagination="{ pageSize: 10 }"
        size="small"
      >
        <template #passRate="{ record }">
          <a-tag :color="record.passRate >= 80 ? 'green' : record.passRate >= 50 ? 'orange' : 'red'">
            {{ record.passRate.toFixed(1) }}%
          </a-tag>
        </template>
      </a-table>

      <a-divider>最近 10 个批次</a-divider>
      <a-table
        :data="recentBatches"
        :columns="batchColumns"
        :pagination="false"
        size="small"
      >
        <template #status="{ record }">
          <a-tag :color="batchStatusColor(record.status)">{{ BATCH_STATUS_LABELS[record.status] }}</a-tag>
        </template>
        <template #rate="{ record }">
          <a-tag :color="record.success_rate >= 80 ? 'green' : 'orange'">
            {{ (record.success_rate ?? 0).toFixed(1) }}%
          </a-tag>
        </template>
      </a-table>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiRecordApi } from '../api'
import { BATCH_STATUS_LABELS, unwrapPage } from '../types'
import type { ApiBatchExecutionRecord, ApiExecutionRecord } from '../types'

const props = defineProps<{ projectId: number | undefined; reloadKey?: number }>()

const loading = ref(false)
const records = ref<ApiExecutionRecord[]>([])
const batches = ref<ApiBatchExecutionRecord[]>([])

const summary = computed(() => {
  const total = records.value.length
  const passed = records.value.filter((r) => r.status === 2).length
  const failed = records.value.filter((r) => r.status === 3).length
  const passRate = total ? Math.round((passed / total) * 1000) / 10 : 0
  return { total, passed, failed, passRate }
})

const trend = computed(() => {
  const now = new Date()
  const days: { date: string; passed: number; failed: number }[] = []
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 24 * 60 * 60 * 1000)
    days.push({ date: d.toISOString().slice(0, 10), passed: 0, failed: 0 })
  }
  const idx: Record<string, { passed: number; failed: number }> = {}
  days.forEach((d) => (idx[d.date] = d))
  records.value.forEach((r) => {
    const start = (r as any).start_time || (r as any).created_at
    if (!start) return
    const date = new Date(start).toISOString().slice(0, 10)
    if (idx[date]) {
      if (r.status === 2) idx[date].passed += 1
      else if (r.status === 3) idx[date].failed += 1
    }
  })
  return days
})

const byCase = computed(() => {
  const map = new Map<string, { name: string; method: string; path: string; total: number; passed: number; failed: number; passRate: number }>()
  records.value.forEach((r: any) => {
    const name = r.test_case_name || `case#${r.test_case}`
    const cur = map.get(name) || { name, method: r.test_case_method || '-', path: r.test_case_path || '-', total: 0, passed: 0, failed: 0, passRate: 0 }
    cur.total += 1
    if (r.status === 2) cur.passed += 1
    if (r.status === 3) cur.failed += 1
    map.set(name, cur)
  })
  const arr = [...map.values()]
  arr.forEach((it) => (it.passRate = it.total ? (it.passed / it.total) * 100 : 0))
  arr.sort((a, b) => b.total - a.total)
  return arr.slice(0, 10)
})

const recentBatches = computed(() => batches.value.slice(0, 10))

const byCaseColumns = [
  { title: '用例', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '方法', dataIndex: 'method', width: 80 },
  { title: '路径', dataIndex: 'path', ellipsis: true, tooltip: true },
  { title: '总数', dataIndex: 'total', width: 80 },
  { title: '通过', dataIndex: 'passed', width: 80 },
  { title: '失败', dataIndex: 'failed', width: 80 },
  { title: '成功率', slotName: 'passRate', width: 100 },
]
const batchColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '名称', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'status', width: 100 },
  { title: '通过/失败/总计', render: (data?: { record?: ApiBatchExecutionRecord }) => { const r = data?.record; return r ? `${r.passed_cases}/${r.failed_cases}/${r.total_cases}` : '-' } },
  { title: '成功率', slotName: 'rate', width: 100 },
  { title: '触发', dataIndex: 'trigger_type', width: 90 },
]

function batchStatusColor(s: number) {
  if (s === 2) return 'green'
  if (s === 3) return 'red'
  if (s === 1) return 'arcoblue'
  return 'gray'
}

function barHeight(v: number) {
  const all: number[] = []
  trend.value.forEach((d) => { all.push(d.passed); all.push(d.failed) })
  const max = Math.max(1, ...all)
  return Math.max(2, (v / max) * 80)
}

async function load() {
  if (!props.projectId) return
  loading.value = true
  try {
    const [recordRes, batchRes] = await Promise.all([
      apiRecordApi.list({ project: props.projectId }),
      apiRecordApi.batches({ project: props.projectId }),
    ])
    records.value = unwrapPage<ApiExecutionRecord>(recordRes).items
    batches.value = unwrapPage<ApiBatchExecutionRecord>(batchRes).items
  } finally {
    loading.value = false
  }
}

watch(() => [props.projectId, props.reloadKey], load, { immediate: true })
</script>

<style scoped>
.reports-wrap {
  padding: 4px 0 24px;
}
.trend-chart {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  height: 100px;
  padding: 0 8px;
}
.trend-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 80px;
}
.bar {
  width: 14px;
  border-radius: 2px 2px 0 0;
  transition: height 0.2s;
}
.bar.passed { background: rgb(var(--green-6)); }
.bar.failed { background: rgb(var(--red-6)); }
.date {
  font-size: 11px;
  color: var(--color-text-3);
}
.empty {
  text-align: center;
  color: var(--color-text-3);
  padding: 24px;
}
</style>
