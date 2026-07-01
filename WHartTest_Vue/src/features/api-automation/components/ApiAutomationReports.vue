<template>
  <div class="reports-wrap">
    <a-spin :loading="loading">
      <!-- 数据统计(累计/通过/失败/成功率、趋势)首页已有,此处不再重复;仅保留报告专属的按接口聚合 -->
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

    </a-spin>

    <a-spin :loading="batchesLoading">
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
        <template #ops="{ record }">
          <a-button type="text" size="mini" @click="openBatchDetail(record)">查看详情</a-button>
        </template>
      </a-table>
    </a-spin>

    <a-modal v-model:visible="detailVisible" :title="`批次详情 #${detailBatch?.id ?? ''} ${detailBatch?.name ?? ''}`" :width="900" :footer="false">
      <a-spin :loading="detailLoading" style="width: 100%">
        <a-descriptions :column="3" size="small" bordered style="margin-bottom: 12px">
          <a-descriptions-item label="状态">
            <a-tag :color="batchStatusColor(detailBatch?.status ?? 0)">{{ BATCH_STATUS_LABELS[detailBatch?.status ?? 0] }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="通过/失败/总计">{{ detailBatch?.passed_cases ?? 0 }}/{{ detailBatch?.failed_cases ?? 0 }}/{{ detailBatch?.total_cases ?? 0 }}</a-descriptions-item>
          <a-descriptions-item label="成功率">{{ (detailBatch?.success_rate ?? 0).toFixed(1) }}%</a-descriptions-item>
        </a-descriptions>
        <div v-if="!detailRecords.length" class="empty">该批次下没有用例执行明细</div>
        <a-table
          v-else
          :data="detailRecords"
          :columns="detailColumns"
          :pagination="{ pageSize: 10 }"
          size="small"
          :scroll="{ x: 700 }"
        >
          <template #recStatus="{ record }">
            <a-tag :color="record.status === 2 ? 'green' : record.status === 3 ? 'red' : 'gray'">{{ STATUS_LABELS[record.status] }}</a-tag>
          </template>
          <template #dur="{ record }">{{ record.duration != null ? record.duration.toFixed(0) + ' ms' : '-' }}</template>
          <template #err="{ record }">
            <a-tooltip v-if="record.error_message" :content="record.error_message">
              <span class="err-text">{{ record.error_message }}</span>
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
import { BATCH_STATUS_LABELS, STATUS_LABELS, unwrapData, unwrapPage } from '../types'
import type { ApiBatchExecutionRecord } from '../types'
import { Message } from '@arco-design/web-vue'

const props = defineProps<{ projectId: number | undefined; reloadKey?: number }>()

const loading = ref(false)
const batchesLoading = ref(false)
const batches = ref<ApiBatchExecutionRecord[]>([])

const detailVisible = ref(false)
const detailLoading = ref(false)
const detailBatch = ref<ApiBatchExecutionRecord | null>(null)
const detailRecords = computed(() => detailBatch.value?.execution_records ?? [])

async function openBatchDetail(record: ApiBatchExecutionRecord) {
  detailBatch.value = record
  detailVisible.value = true
  detailLoading.value = true
  try {
    const res = await apiRecordApi.getBatch(record.id)
    detailBatch.value = unwrapData<ApiBatchExecutionRecord>(res) ?? record
  } catch {
    Message.error('获取批次详情失败')
  } finally {
    detailLoading.value = false
  }
}

const byCase = ref<{ name: string; method: string; path: string; total: number; passed: number; failed: number; passRate: number }[]>([])

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
  { title: '操作', slotName: 'ops', width: 100 },
]
const detailColumns = [
  { title: '用例', dataIndex: 'test_case_name', ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'recStatus', width: 90 },
  { title: '耗时', slotName: 'dur', width: 100 },
  { title: '错误信息', slotName: 'err', ellipsis: true },
]

function batchStatusColor(s: number) {
  if (s === 2) return 'green'
  if (s === 3) return 'red'
  if (s === 1) return 'arcoblue'
  return 'gray'
}

// 批次列表很小、且“查看详情”依赖它，独立加载使其立即渲染；
// 按接口聚合走后端 DB 聚合(execution-records/stats),不再把全部执行记录拉到前端。
async function loadBatches() {
  if (!props.projectId) return
  batchesLoading.value = true
  try {
    const batchRes = await apiRecordApi.batches({ project: props.projectId })
    batches.value = unwrapPage<ApiBatchExecutionRecord>(batchRes).items
  } finally {
    batchesLoading.value = false
  }
}

async function loadStats() {
  if (!props.projectId) return
  loading.value = true
  try {
    const res = await apiRecordApi.stats({ project: props.projectId })
    const data = unwrapData<any>(res) ?? {}
    byCase.value = data.by_case ?? []
  } finally {
    loading.value = false
  }
}

function load() {
  if (!props.projectId) return
  // 两者并行但互不阻塞，各自独立的 loading 状态
  loadBatches()
  loadStats()
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
.err-text {
  color: rgb(var(--red-6));
}
</style>
