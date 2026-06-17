<template>
  <div class="reports-wrap">
    <a-spin :loading="loading">
      <!-- 总览卡片 -->
      <a-grid :cols="4" :col-gap="16" :row-gap="16">
        <a-grid-item>
          <a-card hoverable class="clickable-card" @click="openSummaryDetails('累计执行', records)">
            <a-statistic title="累计执行" :value="summary.total" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card hoverable class="clickable-card" @click="openSummaryDetails('通过', passedRecords)">
            <a-statistic title="通过" :value="summary.passed" :value-style="{ color: 'rgb(var(--green-6))' }" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card hoverable class="clickable-card" @click="openSummaryDetails('失败', failedRecords)">
            <a-statistic title="失败" :value="summary.failed" :value-style="{ color: 'rgb(var(--red-6))' }" />
          </a-card>
        </a-grid-item>
        <a-grid-item>
          <a-card class="summary-card">
            <div class="pass-rate-header">
              <div class="pass-rate-title">成功率</div>
              <div class="pass-rate-value">{{ summary.passRate.toFixed(1) }}%</div>
            </div>
            <a-tooltip :content="`通过 ${summary.passed}｜失败 ${summary.failed}｜总计 ${summary.total}`">
              <div class="pass-rate-pie" :style="{ '--pass-rate': `${summary.passRate}%` }">
                <div class="pass-rate-hole">{{ summary.passRate.toFixed(1) }}%</div>
              </div>
            </a-tooltip>
            <div class="pass-rate-legend">
              <a-tooltip :content="`通过 ${summary.passed}`">
                <div class="legend-item">
                  <span class="legend-dot pass"></span>
                  <span>通过 {{ summary.passed }}</span>
                </div>
              </a-tooltip>
              <a-tooltip :content="`失败 ${summary.failed}`">
                <div class="legend-item">
                  <span class="legend-dot fail"></span>
                  <span>失败 {{ summary.failed }}</span>
                </div>
              </a-tooltip>
            </div>
          </a-card>
        </a-grid-item>
      </a-grid>

      <a-divider>近 7 天趋势</a-divider>
      <div v-if="!trend.length" class="empty">最近 7 天没有执行记录</div>
      <div v-else class="trend-chart">
        <a-tooltip v-for="d in trend" :key="d.date" :content="`${d.date}｜通过 ${d.passed}｜失败 ${d.failed}｜总计 ${d.passed + d.failed}`">
          <div class="trend-col">
            <div class="bars">
              <div class="bar passed" :style="{ height: barHeight(d.passed) + 'px' }"></div>
              <div class="bar failed" :style="{ height: barHeight(d.failed) + 'px' }"></div>
            </div>
            <div class="date">{{ d.date.slice(5) }}</div>
          </div>
        </a-tooltip>
      </div>

      <a-divider>按接口聚合（最近执行优先）</a-divider>
      <a-table
        :data="byCase"
        :columns="byCaseColumns"
        :pagination="{ pageSize: 10 }"
        size="small"
      >
        <template #latestAt="{ record }">{{ formatDateTime(record.latestAt) }}</template>
        <template #passRate="{ record }">
          <a-tag :color="record.passRate >= 80 ? 'green' : record.passRate >= 50 ? 'orange' : 'red'">
            {{ record.passRate.toFixed(1) }}%
          </a-tag>
        </template>
        <template #caseDetail="{ record }">
          <a-button type="text" size="mini" @click="openCaseDetails(record)">查看详情</a-button>
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
        <template #batchDetail="{ record }">
          <a-button type="text" size="mini" @click="openBatchDetails(record)">查看详情</a-button>
        </template>
      </a-table>
    </a-spin>

      <a-modal
      v-model:visible="recordsModalVisible"
      :title="recordsModalTitle"
      width="960px"
      :footer="false"
    >
      <a-table
        :data="recordsModalRows"
        :columns="recordDetailColumns"
        :pagination="recordsPagination"
        size="small"
        @page-change="onRecordsPageChange"
        @page-size-change="onRecordsPageSizeChange"
      >
        <template #detailStatus="{ record }">
          <a-tag :color="record.status === 2 ? 'green' : record.status === 3 ? 'red' : 'gray'">{{ STATUS_LABELS[record.status] }}</a-tag>
        </template>
        <template #detailDuration="{ record }">{{ formatDuration(record.duration) }}</template>
        <template #detailTime="{ record }">{{ formatDateTime((record as any).start_time || record.created_at) }}</template>
        <template #detailError="{ record }">
          <a-tooltip v-if="record.error_message" :content="record.error_message">
            <span class="ellipsis-error">{{ record.error_message }}</span>
          </a-tooltip>
          <span v-else>-</span>
        </template>
      </a-table>
    </a-modal>

    <a-modal
      v-model:visible="batchModalVisible"
      :title="batchModalTitle"
      width="1080px"
      :footer="false"
    >
      <a-spin :loading="batchModalLoading">
        <div v-if="batchModalData" class="batch-summary">
          <a-space wrap>
            <a-tag>{{ BATCH_STATUS_LABELS[batchModalData.status] }}</a-tag>
            <a-tag color="green">通过 {{ batchModalData.passed_cases }}</a-tag>
            <a-tag color="red">失败 {{ batchModalData.failed_cases }}</a-tag>
            <a-tag>总计 {{ batchModalData.total_cases }}</a-tag>
            <a-tag>成功率 {{ (batchModalData.success_rate ?? 0).toFixed(1) }}%</a-tag>
            <a-tag>耗时 {{ formatDuration(batchModalData.duration) }}</a-tag>
          </a-space>
        </div>
        <a-table
          :data="batchModalData?.execution_records || []"
          :columns="recordDetailColumns"
          :pagination="batchRecordsPagination"
          size="small"
          @page-change="onBatchRecordsPageChange"
          @page-size-change="onBatchRecordsPageSizeChange"
        >
          <template #detailStatus="{ record }">
            <a-tag :color="record.status === 2 ? 'green' : record.status === 3 ? 'red' : 'gray'">{{ STATUS_LABELS[record.status] }}</a-tag>
          </template>
          <template #detailDuration="{ record }">{{ formatDuration(record.duration) }}</template>
          <template #detailTime="{ record }">{{ formatDateTime((record as any).start_time || record.created_at) }}</template>
          <template #detailError="{ record }">
            <a-tooltip v-if="record.error_message" :content="record.error_message">
              <span class="ellipsis-error">{{ record.error_message }}</span>
            </a-tooltip>
            <span v-else>-</span>
          </template>
        </a-table>
      </a-spin>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiRecordApi } from '../api'
import { BATCH_STATUS_LABELS, STATUS_LABELS, unwrapPage } from '../types'
import type { ApiBatchExecutionRecord, ApiExecutionRecord } from '../types'

const props = defineProps<{ projectId: number | undefined; reloadKey?: number }>()

const loading = ref(false)
const records = ref<ApiExecutionRecord[]>([])
const batches = ref<ApiBatchExecutionRecord[]>([])
const recordsModalVisible = ref(false)
const recordsModalTitle = ref('')
const recordsModalRows = ref<ApiExecutionRecord[]>([])
const recordsPage = ref(1)
const recordsPageSize = ref(10)
const batchModalVisible = ref(false)
const batchModalTitle = ref('')
const batchModalLoading = ref(false)
const batchModalData = ref<ApiBatchExecutionRecord | null>(null)
const batchRecordsPage = ref(1)
const batchRecordsPageSize = ref(10)

const summary = computed(() => {
  const total = records.value.length
  const passed = records.value.filter((r) => r.status === 2).length
  const failed = records.value.filter((r) => r.status === 3).length
  const passRate = total ? Math.round((passed / total) * 1000) / 10 : 0
  return { total, passed, failed, passRate }
})
const passedRecords = computed(() => records.value.filter((r) => r.status === 2))
const failedRecords = computed(() => records.value.filter((r) => r.status === 3))

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
  const map = new Map<string, { caseId: number; name: string; method: string; path: string; total: number; passed: number; failed: number; passRate: number; latestAt: string }>()
  records.value.forEach((r: any) => {
    const name = r.test_case_name || `case#${r.test_case}`
    const latestAt = (r.start_time || r.created_at || '') as string
    const requestUrl = typeof r.request_data?.url === 'string' ? r.request_data.url : ''
    const path = typeof r.test_case_path === 'string' && r.test_case_path
      ? r.test_case_path
      : requestUrl
    const method = typeof r.test_case_method === 'string' && r.test_case_method
      ? r.test_case_method
      : (typeof r.request_data?.method === 'string' ? r.request_data.method : '-')
    const cur = map.get(name) || { caseId: r.test_case, name, method, path: path || '-', total: 0, passed: 0, failed: 0, passRate: 0, latestAt }
    cur.total += 1
    if (r.status === 2) cur.passed += 1
    if (r.status === 3) cur.failed += 1
    if (latestAt && (!cur.latestAt || new Date(latestAt).getTime() > new Date(cur.latestAt).getTime())) {
      cur.latestAt = latestAt
      if (path) cur.path = path
      if (method && method !== '-') cur.method = method
    }
    map.set(name, cur)
  })
  const arr = [...map.values()]
  arr.forEach((it) => (it.passRate = it.total ? (it.passed / it.total) * 100 : 0))
  arr.sort((a, b) => {
    const diff = new Date(b.latestAt || 0).getTime() - new Date(a.latestAt || 0).getTime()
    return diff || b.total - a.total
  })
  return arr
})

const recentBatches = computed(() => batches.value.slice(0, 10))
const recordsPagination = computed(() => ({
  current: recordsPage.value,
  pageSize: recordsPageSize.value,
  total: recordsModalRows.value.length,
  showPageSize: true,
  pageSizeOptions: [10, 20, 50],
  showTotal: true,
}))
const batchRecordsPagination = computed(() => ({
  current: batchRecordsPage.value,
  pageSize: batchRecordsPageSize.value,
  total: batchModalData.value?.execution_records?.length || 0,
  showPageSize: true,
  pageSizeOptions: [10, 20, 50],
  showTotal: true,
}))

const byCaseColumns = [
  { title: '用例', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '方法', dataIndex: 'method', width: 80 },
  { title: '路径', dataIndex: 'path', ellipsis: true, tooltip: true },
  { title: '最近执行', slotName: 'latestAt', width: 170 },
  { title: '总数', dataIndex: 'total', width: 80 },
  { title: '通过', dataIndex: 'passed', width: 80 },
  { title: '失败', dataIndex: 'failed', width: 80 },
  { title: '成功率', slotName: 'passRate', width: 100 },
  { title: '详情', slotName: 'caseDetail', width: 90 },
]
const batchColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '名称', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'status', width: 100 },
  { title: '通过/失败/总计', render: (data?: { record?: ApiBatchExecutionRecord }) => { const r = data?.record; return r ? `${r.passed_cases}/${r.failed_cases}/${r.total_cases}` : '-' } },
  { title: '成功率', slotName: 'rate', width: 100 },
  { title: '触发', dataIndex: 'trigger_type', width: 90 },
  { title: '详情', slotName: 'batchDetail', width: 90 },
]
const recordDetailColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '用例', dataIndex: 'test_case_name', ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'detailStatus', width: 90 },
  { title: '执行时间', slotName: 'detailTime', width: 170 },
  { title: '耗时', slotName: 'detailDuration', width: 100 },
  { title: '触发', dataIndex: 'trigger_type', width: 90 },
  { title: '错误信息', slotName: 'detailError' },
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

function formatDateTime(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatDuration(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toFixed(3)} s`
}

function onRecordsPageChange(page: number) {
  recordsPage.value = page
}

function onRecordsPageSizeChange(size: number) {
  recordsPageSize.value = size
  recordsPage.value = 1
}

function onBatchRecordsPageChange(page: number) {
  batchRecordsPage.value = page
}

function onBatchRecordsPageSizeChange(size: number) {
  batchRecordsPageSize.value = size
  batchRecordsPage.value = 1
}

function openSummaryDetails(title: string, rows: ApiExecutionRecord[] | Readonly<ApiExecutionRecord[]>) {
  recordsModalTitle.value = `${title}明细`
  recordsModalRows.value = [...rows]
  recordsPage.value = 1
  recordsPageSize.value = 10
  recordsModalVisible.value = true
}

function openCaseDetails(record: { caseId: number; name: string }) {
  recordsModalTitle.value = `接口明细 - ${record.name}`
  recordsModalRows.value = records.value
    .filter((item) => item.test_case === record.caseId)
    .sort((a: any, b: any) => new Date((b.start_time || b.created_at || 0) as string).getTime() - new Date((a.start_time || a.created_at || 0) as string).getTime())
  recordsPage.value = 1
  recordsPageSize.value = 10
  recordsModalVisible.value = true
}

async function openBatchDetails(record: ApiBatchExecutionRecord) {
  batchModalVisible.value = true
  batchModalTitle.value = `批次详情 - ${record.name}`
  batchModalLoading.value = true
  batchRecordsPage.value = 1
  batchRecordsPageSize.value = 10
  try {
    const res = await apiRecordApi.getBatch(record.id)
    batchModalData.value = (res as any)?.data ?? null
  } finally {
    batchModalLoading.value = false
  }
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
.clickable-card {
  cursor: pointer;
}
.batch-summary {
  margin-bottom: 12px;
}
.summary-card {
  min-height: 180px;
}
.pass-rate-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}
.pass-rate-title {
  color: var(--color-text-2);
  font-size: 14px;
}
.pass-rate-value {
  color: rgb(var(--green-6));
  font-size: 18px;
  font-weight: 600;
}
.pass-rate-pie {
  --pass-rate: 0%;
  width: 92px;
  height: 92px;
  margin: 8px auto 10px;
  border-radius: 50%;
  background: conic-gradient(rgb(var(--green-6)) 0 var(--pass-rate), rgb(var(--red-4)) var(--pass-rate) 100%);
  display: flex;
  align-items: center;
  justify-content: center;
}
.pass-rate-hole {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--color-bg-2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-1);
  font-size: 12px;
  font-weight: 600;
}
.pass-rate-legend {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--color-text-2);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.legend-dot.pass {
  background: rgb(var(--green-6));
}
.legend-dot.fail {
  background: rgb(var(--red-4));
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
  cursor: default;
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
.ellipsis-error {
  display: inline-block;
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
