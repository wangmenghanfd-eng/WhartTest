<template>
  <div class="task-center">
    <div v-if="!currentProjectId" class="no-project">
      <a-empty description="请在顶部选择一个项目">
        <template #image>
          <icon-schedule style="font-size: 48px; color: #c2c7d0;" />
        </template>
      </a-empty>
    </div>

    <template v-else>
      <div class="page-header">
        <h1 class="page-title">任务中心</h1>
        <a-button type="primary" @click="handleCreate">
          <template #icon><icon-plus /></template>
          新建任务
        </a-button>
      </div>

      <div class="content-container">
        <div class="filter-row">
          <a-input-search
            v-model="searchKeyword"
            placeholder="搜索任务名称"
            allow-clear
            style="width: 260px"
            @search="handleSearch"
            @clear="handleSearch"
          />
          <a-select
            v-model="statusFilter"
            placeholder="状态筛选"
            allow-clear
            style="width: 120px"
            @change="handleSearch"
          >
            <a-option value="disabled">未启用</a-option>
            <a-option value="running">已启用</a-option>
          </a-select>
          <a-select
            v-model="moduleFilter"
            placeholder="模块筛选"
            allow-clear
            style="width: 130px"
            @change="handleSearch"
          >
            <a-option value="ui_automation">UI 自动化</a-option>
            <a-option value="api_automation">接口自动化</a-option>
            <a-option value="test_suite">测试套件</a-option>
          </a-select>
        </div>

        <a-table
          :columns="columns"
          :data="taskList"
          :loading="loading"
          :pagination="paginationConfig"
          row-key="id"
          @page-change="onPageChange"
          @page-size-change="onPageSizeChange"
        >
          <template #name="{ record }">
            <span class="task-name-text">{{ record.name }}</span>
          </template>

          <template #module="{ record }">
            <a-tag :color="record.module === 'ui_automation' ? 'arcoblue' : record.module === 'api_automation' ? 'green' : 'purple'">
              {{ record.module === 'ui_automation' ? 'UI 自动化' : record.module === 'api_automation' ? '接口自动化' : '测试套件' }}
            </a-tag>
          </template>

          <template #schedule="{ record }">
            {{ record.schedule_display }}
          </template>

          <template #status="{ record }">
            <a-switch
              :model-value="record.status === 'running'"
              size="small"
              @change="(val: string | number | boolean) => handleToggleStatus(record, !!val)"
            />
          </template>

          <template #last_run_at="{ record }">
            {{ record.last_run_at ? formatDate(record.last_run_at) : '—' }}
          </template>

          <template #actions="{ record }">
            <a-space :size="4">
              <a-button type="text" size="small" @click="handleRunNow(record)">
                立即执行
              </a-button>
              <a-button type="text" size="small" @click="handleViewExecutions(record)">
                记录
              </a-button>
              <a-button type="text" size="small" @click="handleEdit(record)">
                编辑
              </a-button>
              <a-popconfirm content="确定要删除此任务吗？" @ok="handleDelete(record)">
                <a-button type="text" size="small" status="danger">删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </a-table>
      </div>

      <a-drawer
        v-model:visible="executionDrawerVisible"
        :title="`执行记录 - ${currentTask?.name || ''}`"
        :width="980"
        :footer="false"
      >
        <a-table
          :columns="executionColumns"
          :data="executionList"
          :loading="executionLoading"
          :pagination="executionPagination"
          row-key="id"
          size="small"
          @page-change="onExecutionPageChange"
        >
          <template #trigger_type="{ record }">
            {{ triggerTextMap[record.trigger_type] }}
          </template>

          <template #status="{ record }">
            <a-tag :color="displayStatusColorMap[record.display_status || record.status]">
              {{ record.display_status_text || execStatusTextMap[record.status] || record.status }}
            </a-tag>
          </template>

          <template #actual_execution_id="{ record }">
            {{ record.actual_execution_id || '—' }}
          </template>

          <template #actual_result="{ record }">
            <a-tag
              v-if="record.actual_result_text"
              :color="actualResultColorMap[record.actual_result_status || 'completed']"
            >
              {{ record.actual_result_text }}
            </a-tag>
            <span v-else>—</span>
          </template>

          <template #actual_duration="{ record }">
            {{ record.actual_duration || '—' }}
          </template>

          <template #actual_summary="{ record }">
            <span class="summary-text">{{ record.actual_summary || '—' }}</span>
          </template>

          <template #started_at="{ record }">
            {{ formatDate(record.started_at) }}
          </template>

          <template #actions="{ record }">
            <a-space :size="4">
              <a-button type="text" size="small" @click="handleViewLog(record)">日志</a-button>
              <a-popconfirm content="确定删除此记录？" @ok="handleDeleteExecution(record)">
                <a-button type="text" size="small" status="danger">删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </a-table>
      </a-drawer>
    </template>

    <TaskFormModal ref="formModalRef" :project-id="currentProjectId!" @success="fetchTasks" />
    <LogViewModal ref="logModalRef" :project-id="currentProjectId!" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { Message } from '@arco-design/web-vue';
import { IconPlus, IconSchedule } from '@arco-design/web-vue/es/icon';
import { useProjectStore } from '@/store/projectStore';
import {
  getTaskList, enableTask, disableTask, runTaskNow,
  deleteTask, getTaskExecutions, deleteExecution,
  type ScheduledTask, type TaskExecution,
} from '../services/taskService';
import TaskFormModal from '../components/TaskFormModal.vue';
import LogViewModal from '../components/LogViewModal.vue';

const projectStore = useProjectStore();
const currentProjectId = computed(() => projectStore.currentProjectId);

const taskList = ref<ScheduledTask[]>([]);
const loading = ref(false);
const searchKeyword = ref('');
const statusFilter = ref<string | undefined>(undefined);
const moduleFilter = ref<string | undefined>(undefined);
const page = ref(1);
const pageSize = ref(10);
const total = ref(0);

const executionDrawerVisible = ref(false);
const currentTask = ref<ScheduledTask | null>(null);
const executionList = ref<TaskExecution[]>([]);
const executionLoading = ref(false);
const executionPage = ref(1);
const executionTotal = ref(0);
const searchTimer = ref<number | null>(null);

const formModalRef = ref<InstanceType<typeof TaskFormModal> | null>(null);
const logModalRef = ref<InstanceType<typeof LogViewModal> | null>(null);

const execStatusTextMap: Record<string, string> = {
  running: '执行中',
  success: '成功',
  failed: '失败',
};

const displayStatusColorMap: Record<string, string> = {
  submitting: 'blue',
  triggered: 'arcoblue',
  failed: 'red',
  running: 'blue',
  success: 'green',
};

const actualResultColorMap: Record<string, string> = {
  pending: 'gray',
  running: 'blue',
  passed: 'green',
  completed: 'arcoblue',
  failed: 'red',
  cancelled: 'orange',
};

const triggerTextMap: Record<string, string> = {
  scheduled: '定时调度',
  manual: '手动执行',
  api: 'API 触发',
};

const paginationConfig = computed(() => ({
  current: page.value,
  pageSize: pageSize.value,
  total: total.value,
  showTotal: true,
  showPageSize: true,
}));

const executionPagination = computed(() => ({
  current: executionPage.value,
  pageSize: 10,
  total: executionTotal.value,
  showTotal: true,
}));

const columns = [
  { title: '任务名称', slotName: 'name', width: 180, align: 'center' as const },
  { title: '模块', slotName: 'module', width: 110, align: 'center' as const },
  { title: '调度策略', slotName: 'schedule', width: 180, align: 'center' as const },
  { title: '状态', slotName: 'status', width: 90, align: 'center' as const },
  { title: '创建人', dataIndex: 'creator_name', width: 100, align: 'center' as const },
  { title: '最近执行', slotName: 'last_run_at', width: 150, align: 'center' as const },
  { title: '操作', slotName: 'actions', width: 260, align: 'center' as const, fixed: 'right' as const },
];

const executionColumns = [
  { title: '执行ID', dataIndex: 'execution_id', width: 180, ellipsis: true },
  { title: '触发方式', slotName: 'trigger_type', width: 90, align: 'center' as const },
  { title: '触发状态', slotName: 'status', width: 90, align: 'center' as const },
  { title: '实际执行ID', slotName: 'actual_execution_id', width: 110, align: 'center' as const },
  { title: '实际结果', slotName: 'actual_result', width: 90, align: 'center' as const },
  { title: '实际耗时', slotName: 'actual_duration', width: 90, align: 'center' as const },
  { title: '结果概览', slotName: 'actual_summary', width: 220, ellipsis: true },
  { title: '开始时间', slotName: 'started_at', width: 150, align: 'center' as const },
  { title: '操作', slotName: 'actions', width: 120, align: 'center' as const },
];

const formatDate = (dateStr: string) => {
  const d = new Date(dateStr);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const fetchTasks = async () => {
  if (!currentProjectId.value) return;
  loading.value = true;
  try {
    const params: Record<string, any> = { page: page.value };
    if (searchKeyword.value) params.search = searchKeyword.value;
    if (statusFilter.value) params.status = statusFilter.value;
    if (moduleFilter.value) params.module = moduleFilter.value;

    const res = await getTaskList(currentProjectId.value, params);
    taskList.value = res.results;
    total.value = res.count;
  } catch (e: any) {
    Message.error(e.response?.data?.detail || '加载任务列表失败');
  } finally {
    loading.value = false;
  }
};

const fetchExecutions = async () => {
  if (!currentProjectId.value || !currentTask.value) return;
  executionLoading.value = true;
  try {
    const res = await getTaskExecutions(
      currentProjectId.value,
      currentTask.value.id,
      { page: executionPage.value },
    );
    executionList.value = res.results;
    executionTotal.value = res.count;
  } catch {
    Message.error('加载执行记录失败');
  } finally {
    executionLoading.value = false;
  }
};

const handleSearch = () => {
  page.value = 1;
  fetchTasks();
};

const handleKeywordInput = () => {
  if (searchTimer.value) {
    window.clearTimeout(searchTimer.value);
  }
  searchTimer.value = window.setTimeout(() => {
    handleSearch();
  }, 250);
};

const onPageChange = (p: number) => {
  page.value = p;
  fetchTasks();
};

const onPageSizeChange = (s: number) => {
  pageSize.value = s;
  page.value = 1;
  fetchTasks();
};

const onExecutionPageChange = (p: number) => {
  executionPage.value = p;
  fetchExecutions();
};

const handleCreate = () => formModalRef.value?.open();
const handleEdit = (task: ScheduledTask) => formModalRef.value?.open(task);

const handleToggleStatus = async (task: ScheduledTask, enabled: boolean) => {
  try {
    if (enabled) {
      await enableTask(currentProjectId.value!, task.id);
      Message.success('任务已启用');
    } else {
      await disableTask(currentProjectId.value!, task.id);
      Message.success('任务已关闭');
    }
    fetchTasks();
  } catch (e: any) {
    Message.error(e.response?.data?.error || '操作失败');
  }
};

const handleRunNow = async (task: ScheduledTask) => {
  try {
    await runTaskNow(currentProjectId.value!, task.id);
    Message.success('任务已提交执行');
    fetchTasks();
  } catch (e: any) {
    Message.error(e.response?.data?.error || '执行失败');
  }
};

const handleDelete = async (task: ScheduledTask) => {
  try {
    await deleteTask(currentProjectId.value!, task.id);
    Message.success('任务已删除');
    fetchTasks();
  } catch {
    Message.error('删除失败');
  }
};

const handleViewExecutions = (task: ScheduledTask) => {
  currentTask.value = task;
  executionPage.value = 1;
  executionDrawerVisible.value = true;
  fetchExecutions();
};

const handleViewLog = (execution: TaskExecution) => {
  logModalRef.value?.open(execution.id);
};

const handleDeleteExecution = async (execution: TaskExecution) => {
  try {
    await deleteExecution(currentProjectId.value!, execution.id);
    Message.success('记录已删除');
    fetchExecutions();
  } catch {
    Message.error('删除失败');
  }
};

watch(currentProjectId, (newId, oldId) => {
  if (newId !== oldId) {
    page.value = 1;
    searchKeyword.value = '';
    statusFilter.value = undefined;
    moduleFilter.value = undefined;
    fetchTasks();
  }
});

watch(searchKeyword, () => {
  handleKeywordInput();
});

onMounted(() => {
  fetchTasks();
});
</script>

<style scoped>
.task-center {
  padding: 20px;
}

.no-project {
  padding: 48px 0;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.content-container {
  background: var(--color-bg-2);
  border-radius: 12px;
  padding: 16px;
}

.filter-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.task-name-text {
  display: inline-block;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-text {
  display: inline-block;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
