<template>
  <div class="dashboard-view">
    <!-- 无项目选择提示 -->
    <div v-if="!currentProjectId" class="no-project-selected">
      <a-empty description="请在顶部选择一个项目查看统计数据">
        <template #image>
          <icon-bar-chart style="font-size: 48px; color: #c2c7d0;" />
        </template>
      </a-empty>
    </div>

    <!-- 仪表盘内容 -->
    <div v-else class="dashboard-content">
      <a-spin :loading="loading" tip="加载中..." class="dashboard-spin">
        <!-- 顶部数据概览 -->
        <div class="overview-section">
          <div class="overview-card">
            <div class="overview-header">
              <icon-file class="overview-icon" />
              <span class="overview-title">功能用例</span>
            </div>
            <div class="overview-card-click" @click="openStatisticsDetail('functional_cases')">
              <div class="overview-value">{{ statistics?.testcases?.total || 0 }}</div>
            </div>
            <div class="overview-sub">
              <span class="sub-item approved">通过 {{ statistics?.testcases?.by_review_status?.approved || 0 }}</span>
              <span class="sub-item pending">待审 {{ statistics?.testcases?.by_review_status?.pending_review || 0 }}</span>
              <span class="sub-item optimization">待优化 {{ statistics?.testcases?.by_review_status?.needs_optimization || 0 }}</span>
              <span class="sub-item opt-pending">优化待审 {{ statistics?.testcases?.by_review_status?.optimization_pending_review || 0 }}</span>
            </div>
          </div>

          <div class="overview-card">
            <div class="overview-header">
              <icon-desktop class="overview-icon" />
              <span class="overview-title">UI自动化</span>
            </div>
            <div class="overview-card-click" @click="openStatisticsDetail('ui_cases')">
              <div class="overview-value">{{ statistics?.ui_automation?.total_cases || 0 }}</div>
            </div>
            <div class="overview-sub">
              <span class="sub-item">执行 {{ statistics?.ui_automation?.total_executions || 0 }}</span>
              <span class="sub-item passed">成功 {{ statistics?.ui_automation?.by_status?.success || 0 }}</span>
              <span class="sub-item failed">失败 {{ statistics?.ui_automation?.by_status?.failed || 0 }}</span>
            </div>
          </div>

          <div class="overview-card">
            <div class="overview-header">
              <icon-code-block class="overview-icon" />
              <span class="overview-title">接口自动化</span>
            </div>
            <div class="overview-card-click" @click="openStatisticsDetail('api_cases')">
              <div class="overview-value">{{ statistics?.api_automation?.total_cases || 0 }}</div>
            </div>
            <div class="overview-sub">
              <span class="sub-item">模块 {{ statistics?.api_automation?.total_modules || 0 }}</span>
              <span class="sub-item">执行 {{ statistics?.api_automation?.total_executions || 0 }}</span>
              <span class="sub-item passed">成功 {{ statistics?.api_automation?.by_status?.success || 0 }}</span>
              <span class="sub-item failed">失败 {{ statistics?.api_automation?.by_status?.failed || 0 }}</span>
            </div>
          </div>

          <div class="overview-card">
            <div class="overview-header">
              <icon-thunderbolt class="overview-icon" />
              <span class="overview-title">功能执行</span>
            </div>
            <div class="overview-card-click" @click="openStatisticsDetail('functional_executions')">
              <div class="overview-value">{{ statistics?.executions?.case_results?.total || 0 }}</div>
            </div>
            <div class="overview-sub">
              <span class="sub-item passed">通过 {{ statistics?.executions?.case_results?.passed || 0 }}</span>
              <span class="sub-item failed">失败 {{ statistics?.executions?.case_results?.failed || 0 }}</span>
              <span class="sub-item optimization">跳过 {{ statistics?.executions?.case_results?.skipped || 0 }}</span>
              <span class="sub-item failed">错误 {{ statistics?.executions?.case_results?.error || 0 }}</span>
            </div>
          </div>

          <div class="overview-card">
            <div class="overview-header">
              <icon-apps class="overview-icon" />
              <span class="overview-title">MCP / Skills</span>
            </div>
            <div class="overview-card-click" @click="openStatisticsDetail('mcp_skills')">
              <div class="overview-value">{{ (statistics?.mcp?.total || 0) + (statistics?.skills?.total || 0) }}</div>
            </div>
            <div class="overview-sub">
              <span class="sub-item">MCP {{ statistics?.mcp?.active || 0 }}/{{ statistics?.mcp?.total || 0 }}</span>
              <span class="sub-item">Skills {{ statistics?.skills?.active || 0 }}/{{ statistics?.skills?.total || 0 }}</span>
            </div>
          </div>
        </div>

        <!-- 主内容区域 -->
        <div class="main-section">
          <!-- 左侧：用例状态分布 -->
          <div class="panel status-panel">
            <div class="panel-header">
              <span class="panel-title">用例审核状态</span>
              <span class="panel-badge">{{ statistics?.testcases?.total || 0 }} 个</span>
            </div>
            <div class="panel-body">
              <div class="status-bars">
                <div
                  class="status-bar-item clickable-row"
                  v-for="item in reviewStatusData"
                  :key="item.key"
                  @click="openStatisticsDetail('functional_cases', item.rawKey)"
                >
                  <div class="bar-header">
                    <span class="bar-label">{{ item.label }}</span>
                    <span class="bar-value">{{ item.value }} <span class="bar-percent">({{ item.percent }}%)</span></span>
                  </div>
                  <div class="bar-track">
                    <div class="bar-fill" :style="{ width: item.percent + '%', background: item.color }"></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 中间：执行通过率环形图 -->
          <div class="panel rate-panel">
            <div class="panel-header">
              <span class="panel-title">执行通过率</span>
            </div>
            <div class="panel-body rate-body">
              <div class="rate-circle">
                <svg viewBox="0 0 100 100" class="rate-svg">
                  <circle cx="50" cy="50" r="42" class="rate-bg" />
                  <circle
                    cx="50" cy="50" r="42"
                    class="rate-progress"
                    :style="{ strokeDasharray: `${passRate * 2.64} 264`, stroke: rateColor }"
                  />
                </svg>
                <div class="rate-text">
                  <span class="rate-value">{{ passRate }}</span>
                  <span class="rate-unit">%</span>
                </div>
              </div>
              <div class="rate-legend">
                <div class="legend-item">
                  <span class="legend-dot passed"></span>
                  <span class="legend-label">通过</span>
                  <span class="legend-value">{{ statistics?.executions?.case_results?.passed || 0 }}</span>
                </div>
                <div class="legend-item">
                  <span class="legend-dot failed"></span>
                  <span class="legend-label">失败</span>
                  <span class="legend-value">{{ statistics?.executions?.case_results?.failed || 0 }}</span>
                </div>
                <div class="legend-item">
                  <span class="legend-dot skipped"></span>
                  <span class="legend-label">跳过</span>
                  <span class="legend-value">{{ statistics?.executions?.case_results?.skipped || 0 }}</span>
                </div>
                <div class="legend-item">
                  <span class="legend-dot error"></span>
                  <span class="legend-label">错误</span>
                  <span class="legend-value">{{ statistics?.executions?.case_results?.error || 0 }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 右侧：Token 使用统计 -->
          <div class="panel resource-panel">
            <div class="panel-header">
              <span class="panel-title">Token 统计（当前用户）</span>
              <div class="token-period-selector">
                <span
                  v-for="opt in periodOptions"
                  :key="opt.value"
                  :class="['period-tag', { active: tokenPeriod === opt.value }]"
                  @click="changeTokenPeriod(opt.value)"
                >{{ opt.label }}</span>
              </div>
            </div>
            <div class="panel-body">
              <div class="resource-grid">
                <div class="resource-block token-total">
                  <div class="resource-label">总消耗</div>
                  <div class="token-value">{{ formatTokenCount(tokenStats?.total?.total_tokens || 0) }}</div>
                  <div class="token-sub">
                    <span class="token-detail">入 {{ formatTokenCount(tokenStats?.total?.input_tokens || 0) }}</span>
                    <span class="token-detail">出 {{ formatTokenCount(tokenStats?.total?.output_tokens || 0) }}</span>
                  </div>
                </div>
                <div class="resource-block">
                  <div class="resource-label">使用情况</div>
                  <div class="resource-stats">
                    <div class="stat-row">
                      <span>请求次数</span>
                      <span class="stat-num">{{ tokenStats?.total?.request_count || 0 }}</span>
                    </div>
                    <div class="stat-row">
                      <span>会话数</span>
                      <span class="stat-num">{{ tokenStats?.total?.session_count || 0 }}</span>
                    </div>
                    <div class="stat-row">
                      <span>平均/请求</span>
                      <span class="stat-num active">{{ avgTokensPerRequest }}</span>
                    </div>
                  </div>
                </div>
                <div class="resource-block">
                  <div class="resource-label">统计周期</div>
                  <div class="resource-stats">
                    <div class="stat-row">
                      <span>开始</span>
                      <span class="stat-num">{{ tokenStats?.period?.start_date || '-' }}</span>
                    </div>
                    <div class="stat-row">
                      <span>结束</span>
                      <span class="stat-num">{{ tokenStats?.period?.end_date || '-' }}</span>
                    </div>
                  </div>
                </div>
                <div class="resource-block" v-if="tokenStats?.by_user?.length">
                  <div class="resource-label">用户排行</div>
                  <div class="resource-stats">
                    <div class="stat-row" v-for="(user, index) in tokenStats.by_user.slice(0, 3)" :key="user.user_id">
                      <span>{{ index + 1 }}. {{ user.username }}</span>
                      <span class="stat-num">{{ formatTokenCount(user.total_tokens) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部：执行趋势 -->
        <div class="trend-section">
          <div class="panel trend-panel">
            <div class="panel-header">
              <span class="panel-title">近7天执行趋势（功能 + UI + 接口）</span>
              <div class="trend-summary">
                <span class="summary-item">
                  近7天: <strong>{{ trendSummary7d.execution_count }}</strong> 次
                </span>
                <span class="summary-item passed">
                  通过 <strong>{{ trendSummary7d.passed }}</strong>
                </span>
                <span class="summary-item failed">
                  失败 <strong>{{ trendSummary7d.failed }}</strong>
                </span>
              </div>
            </div>
            <div class="panel-body">
              <div class="trend-chart">
                <a-tooltip
                  v-for="(day, index) in statistics?.execution_trend?.daily_7d || []"
                  :key="index"
                  :content="`${day.date}｜执行 ${day.execution_count}｜通过 ${day.passed}｜失败 ${day.failed}`"
                >
                  <div class="trend-column">
                    <div class="column-bars">
                      <div
                        class="column-bar passed"
                        :style="{ height: getBarHeight(day.passed) }"
                      ></div>
                      <div
                        class="column-bar failed"
                        :style="{ height: getBarHeight(day.failed) }"
                      ></div>
                    </div>
                    <div class="column-label">{{ formatDate(day.date) }}</div>
                  </div>
                </a-tooltip>
              </div>
              <div class="trend-legend">
                <span class="legend-tag passed">通过</span>
                <span class="legend-tag failed">失败</span>
              </div>
            </div>
          </div>
        </div>
      </a-spin>
    </div>

    <a-modal
      v-model:visible="detailVisible"
      :title="detailTitle"
      width="980px"
      :footer="false"
    >
      <a-table
        :data="detailRows"
        :columns="detailColumns"
        :loading="detailLoading"
        :pagination="detailPagination"
        size="small"
        @page-change="onDetailPageChange"
        @page-size-change="onDetailPageSizeChange"
      >
        <template #detailStatus="{ record }">
          <a-tag :color="getStatusTagColor(record.status)">{{ record.status }}</a-tag>
        </template>
        <template #detailUpdated="{ record }">{{ formatDateTime(record.updated_at) }}</template>
        <template #detailExtra="{ record }">
          <a-tooltip :content="record.extra">
            <span class="detail-ellipsis">{{ record.extra }}</span>
          </a-tooltip>
        </template>
      </a-table>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { Message } from '@arco-design/web-vue';
import {
  IconBarChart, IconFile, IconThunderbolt, IconApps, IconDesktop, IconCodeBlock
} from '@arco-design/web-vue/es/icon';
import {
  getProjectStatistics,
  getProjectStatisticsDetail,
  getTokenUsageStats,
  type ProjectStatistics,
  type TokenUsageStats,
  type ProjectStatisticsDetailRow,
} from '@/services/projectService';
import { useProjectStore } from '@/store/projectStore';

const projectStore = useProjectStore();
const loading = ref(false);
const statistics = ref<ProjectStatistics | null>(null);
const tokenStats = ref<TokenUsageStats | null>(null);
const tokenPeriod = ref<'day' | 'week' | 'month'>('day');
const detailVisible = ref(false);
const detailLoading = ref(false);
const detailTitle = ref('');
const detailKind = ref<'functional_cases' | 'ui_cases' | 'api_cases' | 'functional_executions' | 'mcp_skills'>('functional_cases');
const detailReviewStatus = ref<string | undefined>(undefined);
const detailRows = ref<ProjectStatisticsDetailRow[]>([]);
const detailPage = ref(1);
const detailPageSize = ref(10);
const detailTotal = ref(0);

const periodOptions = [
  { label: '日', value: 'day' as const },
  { label: '周', value: 'week' as const },
  { label: '月', value: 'month' as const },
];

const currentProjectId = computed(() => projectStore.currentProjectId);

const passRate = computed(() => {
  const total = statistics.value?.executions?.case_results?.total || 0;
  const passed = statistics.value?.executions?.case_results?.passed || 0;
  if (total === 0) return 0;
  return Math.round((passed / total) * 100);
});

const rateColor = computed(() => {
  if (passRate.value >= 80) return '#52c41a';
  if (passRate.value >= 60) return '#faad14';
  return '#ff4d4f';
});

const reviewStatusData = computed(() => {
  const total = statistics.value?.testcases?.total || 0;
  const getPercent = (val: number) => total === 0 ? 0 : Math.round((val / total) * 100);
  const statuses = statistics.value?.testcases?.by_review_status;

  return [
    { key: 'approved', rawKey: 'approved', label: '已通过', value: statuses?.approved || 0, percent: getPercent(statuses?.approved || 0), color: '#52c41a' },
    { key: 'pending', rawKey: 'pending_review', label: '待审核', value: statuses?.pending_review || 0, percent: getPercent(statuses?.pending_review || 0), color: '#faad14' },
    { key: 'optimization', rawKey: 'needs_optimization', label: '待优化', value: statuses?.needs_optimization || 0, percent: getPercent(statuses?.needs_optimization || 0), color: '#1890ff' },
    { key: 'opt_pending', rawKey: 'optimization_pending_review', label: '优化待审', value: statuses?.optimization_pending_review || 0, percent: getPercent(statuses?.optimization_pending_review || 0), color: '#722ed1' },
    { key: 'unavailable', rawKey: 'unavailable', label: '不可用', value: statuses?.unavailable || 0, percent: getPercent(statuses?.unavailable || 0), color: '#ff4d4f' },
  ];
});

const trendSummary7d = computed(() => {
  const daily = statistics.value?.execution_trend?.daily_7d || [];
  return daily.reduce(
    (acc, item) => {
      acc.execution_count += item.execution_count || 0;
      acc.passed += item.passed || 0;
      acc.failed += item.failed || 0;
      return acc;
    },
    { execution_count: 0, passed: 0, failed: 0 }
  );
});

const detailPagination = computed(() => ({
  current: detailPage.value,
  pageSize: detailPageSize.value,
  total: detailTotal.value,
  showTotal: true,
  showPageSize: true,
  pageSizeOptions: [10, 20, 50],
}));

const detailColumns = computed(() => {
  const base = [
    { title: 'ID', dataIndex: 'id', width: 100 },
    { title: '名称', dataIndex: 'name', ellipsis: true, tooltip: true },
    { title: '模块/分类', dataIndex: 'module', width: 160, ellipsis: true, tooltip: true },
    { title: '状态', slotName: 'detailStatus', width: 120 },
  ];
  if (detailKind.value === 'mcp_skills') {
    return [
      ...base,
      { title: '更新时间', slotName: 'detailUpdated', width: 180 },
    ];
  }
  return [
    ...base,
    { title: '详情', slotName: 'detailExtra', ellipsis: true, tooltip: true },
    { title: '更新时间', slotName: 'detailUpdated', width: 180 },
  ];
});

const getBarHeight = (value: number): string => {
  const maxValue = Math.max(
    ...(statistics.value?.execution_trend?.daily_7d?.map(d => Math.max(d.passed, d.failed)) || [1])
  );
  if (maxValue === 0) return '4px';
  const height = Math.max(4, (value / maxValue) * 80);
  return height + 'px';
};

// 统一按阿布扎比/迪拜时区(UTC+4)显示,不随浏览器/系统时区变化
const APP_TZ = 'Asia/Dubai';
const dubaiParts = (date: Date) => {
  const p = new Intl.DateTimeFormat('en-CA', {
    timeZone: APP_TZ, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(date);
  return Object.fromEntries(p.map((x) => [x.type, x.value])) as Record<string, string>;
};

const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr || '';
  const p = dubaiParts(date);
  return `${Number(p.month)}/${Number(p.day)}`;
};

const formatDateTime = (dateStr: string): string => {
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr || '-';
  const p = dubaiParts(date);
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
};

const formatTokenCount = (count: number): string => {
  return count.toLocaleString('zh-CN');
};

const avgTokensPerRequest = computed(() => {
  const total = tokenStats.value?.total?.total_tokens || 0;
  const requests = tokenStats.value?.total?.request_count || 0;
  if (requests === 0) return '0';
  return formatTokenCount(Math.round(total / requests));
});

const getStatusTagColor = (status: string) => {
  if (['成功', '已通过', '启用', '已完成', '通过'].includes(status)) return 'green';
  if (['失败', '不可用', '停用'].includes(status)) return 'red';
  if (['待审核', '待优化', '优化待审', '执行中'].includes(status)) return 'orange';
  return 'arcoblue';
};

const fetchStatisticsDetail = async () => {
  if (!currentProjectId.value) return;
  detailLoading.value = true;
  try {
    const response = await getProjectStatisticsDetail(currentProjectId.value, {
      kind: detailKind.value,
      review_status: detailReviewStatus.value,
      page: detailPage.value,
      page_size: detailPageSize.value,
    });
    if (response.success && response.data) {
      detailTitle.value = response.data.title;
      detailRows.value = response.data.results;
      detailTotal.value = response.data.count;
    } else {
      Message.error(response.error || '获取详情失败');
    }
  } finally {
    detailLoading.value = false;
  }
};

const openStatisticsDetail = (
  kind: 'functional_cases' | 'ui_cases' | 'api_cases' | 'functional_executions' | 'mcp_skills',
  reviewStatus?: string
) => {
  detailKind.value = kind;
  detailReviewStatus.value = reviewStatus;
  detailPage.value = 1;
  detailPageSize.value = 10;
  detailVisible.value = true;
  fetchStatisticsDetail();
};

const onDetailPageChange = (page: number) => {
  detailPage.value = page;
  fetchStatisticsDetail();
};

const onDetailPageSizeChange = (pageSize: number) => {
  detailPageSize.value = pageSize;
  detailPage.value = 1;
  fetchStatisticsDetail();
};

const fetchTokenStats = async () => {
  try {
    const response = await getTokenUsageStats({ group_by: tokenPeriod.value });
    if (response.success && response.data) {
      tokenStats.value = response.data;
    }
  } catch (error) {
    console.error('获取 Token 统计数据出错:', error);
  }
};

const changeTokenPeriod = (period: 'day' | 'week' | 'month') => {
  tokenPeriod.value = period;
  fetchTokenStats();
};

const fetchStatistics = async () => {
  if (!currentProjectId.value) return;

  loading.value = true;
  try {
    const response = await getProjectStatistics(currentProjectId.value);
    console.log('Statistics API response:', response);
    if (response.success && response.data) {
      statistics.value = response.data;
      console.log('Statistics data:', statistics.value);
    } else {
      console.error('Statistics API error:', response.error);
      Message.error(response.error || '获取统计数据失败');
    }
  } catch (error) {
    console.error('获取统计数据出错:', error);
    Message.error('获取统计数据时发生错误');
  } finally {
    loading.value = false;
  }
};

watch(currentProjectId, () => {
  if (currentProjectId.value) {
    fetchStatistics();
  } else {
    statistics.value = null;
  }
});

onMounted(() => {
  fetchTokenStats();
  if (currentProjectId.value) {
    fetchStatistics();
  }
});
</script>

<style scoped>
.dashboard-view {
  height: 100%;
  background-color: var(--theme-page-bg);
  padding: 10px;
  box-sizing: border-box;
  overflow-y: auto;
}

.no-project-selected {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
}

.dashboard-content {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.dashboard-spin {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
}

:deep(.arco-spin-children) {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 顶部概览卡片 */
.overview-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}

.overview-card {
  background: var(--color-bg-2);
  border-radius: 8px;
  padding: 16px 20px;
  transition: all 0.2s;
  box-shadow: 4px 0 10px rgba(0, 0, 0, 0.2), 0 4px 10px rgba(0, 0, 0, 0.2), 0 0 10px rgba(0, 0, 0, 0.15);
}

.overview-card:hover {
  box-shadow: 4px 0 12px rgba(var(--theme-accent-rgb), 0.22), 0 4px 12px rgba(var(--theme-accent-rgb), 0.22), 0 0 12px rgba(var(--theme-accent-rgb), 0.18);
}

.overview-card-click {
  cursor: pointer;
}

.overview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.overview-icon {
  font-size: 20px;
  color: var(--theme-accent);
}

.overview-title {
  font-size: 14px;
  color: var(--theme-text-secondary);
  font-weight: 500;
}

.overview-value {
  font-size: 28px;
  font-weight: 600;
  color: #1d2129;
  line-height: 1.2;
  margin-bottom: 8px;
}

.overview-sub {
  display: flex;
  flex-wrap: nowrap;
  justify-content: space-between;
  gap: 4px;
  font-size: 12px;
  color: #86909c;
}

.sub-item {
  flex: 1;
  text-align: center;
  min-width: 0;
  white-space: nowrap;
}

.sub-item.approved, .sub-item.active, .sub-item.passed { color: #52c41a; }
.sub-item.pending, .sub-item.draft { color: #faad14; }
.sub-item.failed { color: #ff4d4f; }
.sub-item.optimization { color: #1890ff; }
.sub-item.opt-pending { color: #722ed1; }

/* 主内容区域 */
.main-section {
  display: grid;
  grid-template-columns: minmax(340px, 1fr) 280px minmax(380px, 1fr);
  gap: 10px;
  align-items: stretch;
}

.panel {
  background: var(--color-bg-2);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 4px 0 10px rgba(0, 0, 0, 0.2), 0 4px 10px rgba(0, 0, 0, 0.2), 0 0 10px rgba(0, 0, 0, 0.15);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid var(--theme-border);
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #1d2129;
}

.panel-badge {
  font-size: 12px;
  color: var(--theme-text-tertiary);
  background: var(--theme-surface-soft);
  padding: 2px 8px;
  border-radius: 10px;
}

.panel-body {
  padding: 16px 20px;
}

/* 状态条形图 */
.status-bars {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.status-bar-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  transition: background-color 0.2s ease, transform 0.2s ease;
}

.status-bar-item:hover {
  background: rgba(var(--theme-accent-rgb), 0.06);
}

.bar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.bar-label {
  font-size: 13px;
  color: var(--theme-text-secondary);
}

.bar-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--theme-text);
}

.bar-percent {
  font-size: 12px;
  font-weight: 400;
  color: var(--theme-text-tertiary);
}

.bar-track {
  height: 6px;
  background: var(--theme-surface-soft);
  border-radius: 3px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

/* 通过率环形图 */
.rate-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.rate-circle {
  position: relative;
  width: 120px;
  height: 120px;
}

.rate-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.rate-bg {
  fill: none;
  stroke: var(--theme-surface-soft);
  stroke-width: 8;
}

.rate-progress {
  fill: none;
  stroke-width: 8;
  stroke-linecap: round;
  transition: stroke-dasharray 0.5s ease;
}

.rate-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}

.rate-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--theme-text);
}

.rate-unit {
  font-size: 14px;
  color: var(--theme-text-tertiary);
}

.rate-legend {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
  width: 100%;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-dot.passed { background: #52c41a; }
.legend-dot.failed { background: #ff4d4f; }
.legend-dot.skipped { background: #faad14; }
.legend-dot.error { background: #ff7875; }

.legend-label {
  color: var(--theme-text-tertiary);
  flex: 1;
}

.legend-value {
  font-weight: 600;
  color: var(--theme-text);
}

/* 资源统计 */
.resource-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 16px;
}

.resource-block {
  min-width: 0;
  padding: 0 0 12px;
  border-bottom: 1px solid var(--theme-border);
}

.resource-block:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.resource-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--theme-text-secondary);
  margin-bottom: 8px;
}

.resource-stats {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--theme-text-tertiary);
}

.stat-num {
  font-weight: 600;
  color: var(--theme-text);
}

.stat-num.active { color: #52c41a; }
.stat-num.deprecated { color: #ff4d4f; }

/* Token 统计样式 */
.token-period-selector {
  display: flex;
  gap: 4px;
}

.period-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  cursor: pointer;
  color: var(--theme-text-tertiary);
  background: var(--theme-surface-soft);
  transition: all 0.2s;
}

.period-tag:hover {
  color: var(--theme-accent);
}

.period-tag.active {
  color: #fff;
  background: var(--theme-accent);
}

.token-total {
  text-align: center;
  padding-bottom: 16px !important;
  grid-column: 1 / -1;
}

.token-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--theme-accent);
  line-height: 1.2;
  margin: 8px 0;
}

.token-sub {
  display: flex;
  justify-content: center;
  gap: 16px;
}

.token-detail {
  font-size: 12px;
  color: var(--theme-text-tertiary);
}

/* 趋势图 */
.trend-section {
  margin-top: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 180px;
}

.trend-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.trend-panel .panel-header {
  flex-wrap: wrap;
  gap: 12px;
}

.trend-panel .panel-body {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.trend-summary {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--theme-text-tertiary);
}

.summary-item strong {
  color: var(--theme-text);
}

.summary-item.passed strong { color: #52c41a; }
.summary-item.failed strong { color: #ff4d4f; }

.trend-chart {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex: 1;
  min-height: 100px;
  padding: 10px 0;
}

.trend-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: default;
}

.column-bars {
  display: flex;
  gap: 3px;
  align-items: flex-end;
  height: 80px;
}

.column-bar {
  width: 12px;
  border-radius: 2px 2px 0 0;
  transition: height 0.3s;
}

.column-bar.passed { background: #52c41a; }
.column-bar.failed { background: #ff4d4f; }

.column-label {
  font-size: 11px;
  color: var(--theme-text-tertiary);
}

.trend-legend {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--theme-border);
}

.legend-tag {
  font-size: 12px;
  color: var(--theme-text-tertiary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-tag::before {
  content: '';
  width: 12px;
  height: 8px;
  border-radius: 2px;
}

.legend-tag.passed::before { background: #52c41a; }
.legend-tag.failed::before { background: #ff4d4f; }

.clickable-row {
  cursor: pointer;
}

.detail-ellipsis {
  display: inline-block;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 响应式 */
@media (max-width: 1200px) {
  .overview-section {
    grid-template-columns: repeat(2, 1fr);
  }

  .main-section {
    grid-template-columns: 1fr;
  }

  .rate-panel {
    order: -1;
  }

  .resource-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .overview-section {
    grid-template-columns: 1fr;
  }

  .trend-summary {
    flex-wrap: wrap;
  }
}
</style>
