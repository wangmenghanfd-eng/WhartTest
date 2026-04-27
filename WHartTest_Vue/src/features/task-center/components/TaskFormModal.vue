<template>
  <a-modal
    v-model:visible="visible"
    :title="isEditing ? '编辑定时任务' : '新建定时任务'"
    :width="720"
    :mask-closable="false"
    @cancel="handleClose"
  >
    <template #footer>
        <a-space>
          <a-button @click="handleClose">取消</a-button>
          <a-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ isEditing ? '保存' : '保存并启用' }}
          </a-button>
        </a-space>
      </template>

    <div class="form-scroll-area">
      <a-form :model="form" layout="vertical" ref="formRef" size="small">
        <a-form-item label="任务名称" field="name" :rules="[{ required: true, message: '请输入任务名称' }]">
          <a-input v-model="form.name" placeholder="如 UI-登录页-每日" :max-length="50" show-word-limit />
        </a-form-item>

        <a-form-item label="任务描述" field="description">
          <a-textarea v-model="form.description" placeholder="用于说明任务目的" :max-length="200" :auto-size="{ minRows: 2, maxRows: 3 }" />
        </a-form-item>

        <!-- 所属模块 + UI用例选择 同行 -->
        <div class="form-row">
          <a-form-item label="所属模块" field="module" :rules="[{ required: true, message: '请选择' }]">
            <a-select v-model="form.module" placeholder="请选择模块" @change="onModuleChange">
              <a-option value="ui_automation">UI 自动化</a-option>
              <a-option value="api_automation">接口自动化</a-option>
              <a-option value="test_suite">测试套件</a-option>
            </a-select>
          </a-form-item>

          <a-form-item
            v-if="form.module === 'ui_automation'"
            label="选择UI用例"
            field="ui_testcase_ids"
            :rules="[{ required: true, message: '请选择至少一个UI用例' }]"
          >
            <a-button type="outline" size="small" @click="openCaseSelectModal">
              <template #icon><icon-select-all /></template>
              {{ form.ui_testcase_ids.length ? `已选 ${form.ui_testcase_ids.length} 个用例` : '选择用例' }}
            </a-button>
          </a-form-item>

          <a-form-item
            v-if="form.module === 'api_automation'"
            label="选择接口用例"
            field="api_testcase_ids"
            :rules="[{ required: true, message: '请选择至少一个接口用例' }]"
          >
            <a-button type="outline" size="small" @click="openApiCaseSelectModal">
              <template #icon><icon-select-all /></template>
              {{ form.api_testcase_ids.length ? `已选 ${form.api_testcase_ids.length} 个用例` : '选择接口用例' }}
            </a-button>
          </a-form-item>

          <a-form-item
            v-if="form.module === 'test_suite'"
            label="选择测试套件"
            field="test_suite"
            :rules="[{ required: true, message: '请选择测试套件' }]"
          >
            <a-select v-model="form.test_suite" placeholder="请选择" :loading="loadingSuites" allow-search @popup-visible-change="(v: boolean) => v && loadTestSuites()">
              <a-option
                v-if="form.test_suite && missingSelectedSuiteLabel"
                :key="form.test_suite"
                :value="form.test_suite"
              >
                {{ missingSelectedSuiteLabel }}
              </a-option>
              <a-option v-for="s in testSuites" :key="s.id" :value="s.id">{{ s.name }}</a-option>
            </a-select>
          </a-form-item>
        </div>

        <!-- 执行器 + 调度策略 + 执行时间 同行 -->
        <div v-if="form.module === 'ui_automation'" class="form-row-3">
          <a-form-item
            label="执行器"
            field="actuator_id"
            :rules="[{ required: true, message: '请选择执行器' }]"
          >
            <a-select v-model="form.actuator_id" placeholder="请选择执行器" :loading="loadingActuators" allow-search @popup-visible-change="(v: boolean) => v && loadActuators()">
              <a-option v-for="a in actuators" :key="a.id" :value="a.id">
                {{ a.name || a.id }} ({{ a.ip }})
              </a-option>
            </a-select>
          </a-form-item>
          <a-form-item label="调度策略" field="schedule_type" :rules="[{ required: true, message: '请选择' }]">
            <a-select v-model="form.schedule_type" placeholder="请选择">
              <a-option value="once">仅一次</a-option>
              <a-option value="daily">每天</a-option>
              <a-option value="weekly">每周</a-option>
              <a-option value="hourly">每小时</a-option>
            </a-select>
          </a-form-item>
          <a-form-item v-if="form.schedule_type === 'once'" label="执行时间" field="once_datetime" :rules="[{ required: true, message: '请选择' }]">
            <a-date-picker v-model="form.once_datetime" show-time format="YYYY-MM-DD HH:mm" placeholder="选择时间" style="width: 100%" />
          </a-form-item>
          <a-form-item v-if="form.schedule_type === 'daily'" label="执行时间" field="daily_time" :rules="[{ required: true, message: '请选择' }]">
            <a-time-picker v-model="form.daily_time" format="HH:mm" placeholder="选择时间" style="width: 100%" />
          </a-form-item>
          <a-form-item v-if="form.schedule_type === 'hourly'" label="第几分钟执行" field="hourly_minute" :rules="[{ required: true, message: '请输入' }]">
            <a-input-number v-model="form.hourly_minute" :min="0" :max="59" placeholder="0-59" style="width: 100%">
              <template #suffix>分</template>
            </a-input-number>
          </a-form-item>
        </div>

        <div v-if="form.module === 'ui_automation'" class="form-tip">
          UI 自动化定时任务依赖所选执行器保持在线。若执行器页面断开，或连接没有落在当前处理调度的后端进程，任务可能提示“执行器不在线”。
        </div>

        <div v-if="form.module === 'api_automation'" class="form-tip">
          接口自动化定时任务由后端 Celery/httpx 直接执行，不依赖浏览器执行器。建议优先为接口用例配置默认环境。
        </div>

        <!-- 非UI自动化模块：调度策略 + 执行时间 同行 -->
        <div v-if="form.module !== 'ui_automation'" class="form-row">
          <a-form-item label="调度策略" field="schedule_type" :rules="[{ required: true, message: '请选择' }]">
            <a-select v-model="form.schedule_type" placeholder="请选择">
              <a-option value="once">仅一次</a-option>
              <a-option value="daily">每天</a-option>
              <a-option value="weekly">每周</a-option>
              <a-option value="hourly">每小时</a-option>
            </a-select>
          </a-form-item>
          <a-form-item v-if="form.schedule_type === 'once'" label="执行时间" field="once_datetime" :rules="[{ required: true, message: '请选择' }]">
            <a-date-picker v-model="form.once_datetime" show-time format="YYYY-MM-DD HH:mm" placeholder="选择时间" style="width: 100%" />
          </a-form-item>
          <a-form-item v-if="form.schedule_type === 'daily'" label="执行时间" field="daily_time" :rules="[{ required: true, message: '请选择' }]">
            <a-time-picker v-model="form.daily_time" format="HH:mm" placeholder="选择时间" style="width: 100%" />
          </a-form-item>
          <a-form-item v-if="form.schedule_type === 'hourly'" label="第几分钟执行" field="hourly_minute" :rules="[{ required: true, message: '请输入' }]">
            <a-input-number v-model="form.hourly_minute" :min="0" :max="59" placeholder="0-59" style="width: 100%">
              <template #suffix>分</template>
            </a-input-number>
          </a-form-item>
        </div>

        <div v-if="form.schedule_type === 'once'" class="form-tip">
          “仅一次”适合验证任务是否会准点触发。请设置未来 2 到 3 分钟的时间，到点执行后任务会自动停用。
        </div>

        <div v-if="form.schedule_type === 'daily' || form.schedule_type === 'weekly' || form.schedule_type === 'hourly'" class="form-row">
          <a-form-item label="时区" field="task_timezone">
            <a-select v-model="form.task_timezone" placeholder="请选择时区">
              <a-option value="Asia/Shanghai">Asia/Shanghai (UTC+8)</a-option>
              <a-option value="Asia/Dubai">Asia/Dubai (UTC+4)</a-option>
              <a-option value="Asia/Kolkata">Asia/Kolkata (UTC+5:30)</a-option>
              <a-option value="Europe/London">Europe/London (UTC+0/+1)</a-option>
              <a-option value="Europe/Berlin">Europe/Berlin (UTC+1/+2)</a-option>
              <a-option value="America/New_York">America/New_York (UTC-5/-4)</a-option>
              <a-option value="America/Los_Angeles">America/Los_Angeles (UTC-8/-7)</a-option>
              <a-option value="UTC">UTC (UTC+0)</a-option>
            </a-select>
          </a-form-item>
        </div>

        <div v-if="form.schedule_type === 'daily' || form.schedule_type === 'weekly'" class="form-tip">
          执行时间按所选时区解释。若当前时间已过今天的时刻，下次从下一个周期开始执行。
        </div>

        <!-- 每周额外显示星期选择和时间 -->
        <template v-if="form.schedule_type === 'weekly'">
          <a-form-item label="选择星期" field="weekly_days" :rules="[{ required: true, message: '请至少选一天' }]">
            <a-checkbox-group v-model="form.weekly_days">
              <a-checkbox v-for="day in weekDayOptions" :key="day.value" :value="day.value">{{ day.label }}</a-checkbox>
            </a-checkbox-group>
          </a-form-item>
          <a-form-item label="执行时间" field="weekly_time" :rules="[{ required: true, message: '请选择' }]">
            <a-time-picker v-model="form.weekly_time" format="HH:mm" placeholder="选择时间" style="width: 100%" />
          </a-form-item>
        </template>

        <!-- 重试策略 -->
        <a-form-item label="失败重试">
          <a-switch v-model="form.retry_enabled" />
        </a-form-item>
        <div v-if="form.retry_enabled" class="retry-config">
          <a-form-item label="重试次数">
            <a-input-number v-model="form.retry_count" :min="1" :max="5" style="width: 100%" />
          </a-form-item>
          <a-form-item label="重试间隔">
            <a-input-number v-model="form.retry_interval" :min="1" :max="30" style="width: 100%">
              <template #suffix>分</template>
            </a-input-number>
          </a-form-item>
        </div>
      </a-form>
    </div>
  </a-modal>
  <UiTestCaseSelectModal ref="caseSelectModal" :project-id="projectId" @confirm="onCaseSelected" />
  <ApiTestCaseSelectModal ref="apiCaseSelectModal" :project-id="projectId" @confirm="onApiCaseSelected" />
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue';
import { Message } from '@arco-design/web-vue';
import axios from 'axios';
import { API_BASE_URL } from '@/config/api';
import { useAuthStore } from '@/store/authStore';
import { createTask, updateTask, type TaskFormData, type ScheduledTask } from '../services/taskService';
import { actuatorApi, type ActuatorInfo } from '@/features/ui-automation/api';
import UiTestCaseSelectModal from './UiTestCaseSelectModal.vue';
import ApiTestCaseSelectModal from './ApiTestCaseSelectModal.vue';

const props = defineProps<{
  projectId: number;
}>();

const emit = defineEmits<{
  (e: 'success'): void;
}>();

const visible = ref(false);
const submitting = ref(false);
const isEditing = ref(false);
const editingId = ref<number | null>(null);
const formRef = ref();

// 下拉数据
const loadingSuites = ref(false);
const loadingActuators = ref(false);
const testSuites = ref<{ id: number; name: string }[]>([]);
const actuators = ref<ActuatorInfo[]>([]);
const caseSelectModal = ref<InstanceType<typeof UiTestCaseSelectModal>>();
const apiCaseSelectModal = ref<InstanceType<typeof ApiTestCaseSelectModal>>();
const editingTaskMeta = ref<ScheduledTask | null>(null);

const weekDayOptions = [
  { value: 0, label: '周一' },
  { value: 1, label: '周二' },
  { value: 2, label: '周三' },
  { value: 3, label: '周四' },
  { value: 4, label: '周五' },
  { value: 5, label: '周六' },
  { value: 6, label: '周日' },
];

const defaultForm = (): TaskFormData => ({
  name: '',
  description: '',
  module: 'ui_automation',
  execution_target: 'actuator',
  schedule_type: 'daily',
  once_datetime: null,
  daily_time: null,
  weekly_days: [],
  weekly_time: null,
  hourly_minute: null,
  task_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai',
  retry_enabled: false,
  retry_count: 3,
  retry_interval: 2,
  test_suite: null,
  ui_testcase_ids: [],
  api_testcase_ids: [],
  actuator_id: '',
});

const form = reactive<TaskFormData>(defaultForm());

const getHeaders = () => {
  const authStore = useAuthStore();
  return { Authorization: `Bearer ${authStore.getAccessToken}` };
};

const loadTestSuites = async () => {
  loadingSuites.value = true;
  try {
    const response = await axios.get(`${API_BASE_URL}/projects/${props.projectId}/test-suites/`, {
      headers: getHeaders(),
    });
    const resData = response.data;
    let list: any[] = [];
    if (resData?.status === 'success') {
      list = Array.isArray(resData.data) ? resData.data : resData.data?.results || [];
    } else {
      list = resData?.results || resData?.data || [];
    }
    testSuites.value = list.map((s: any) => ({ id: s.id, name: s.name }));
  } catch {
    testSuites.value = [];
  } finally {
    loadingSuites.value = false;
  }
};

const loadActuators = async () => {
  loadingActuators.value = true;
  try {
    const res = await actuatorApi.list();
    const innerData = (res as any).data?.data?.data;
    actuators.value = (innerData?.items || []).filter((a: ActuatorInfo) => a.is_open);
  } catch {
    actuators.value = [];
  } finally {
    loadingActuators.value = false;
  }
};

const onModuleChange = () => {
  form.test_suite = null;
  form.ui_testcase_ids = [];
  form.api_testcase_ids = [];
  form.actuator_id = '';
  if (form.module === 'test_suite') {
    form.execution_target = 'actuator';
    void loadTestSuites();
  }
  if (form.module === 'ui_automation') {
    form.execution_target = 'actuator';
    void loadActuators();
  }
  if (form.module === 'api_automation') {
    form.execution_target = 'backend';
  }
};

const resetForm = () => {
  Object.assign(form, defaultForm());
};

const normalizeOnceDateTime = (value: unknown): string | null => {
  if (!value) return null;

  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value.toISOString();
  }

  if (typeof value === 'object') {
    const candidate = value as {
      toDate?: () => Date;
      toISOString?: () => string;
      valueOf?: () => number;
    };

    if (typeof candidate.toDate === 'function') {
      const date = candidate.toDate();
      return Number.isNaN(date.getTime()) ? null : date.toISOString();
    }

    if (typeof candidate.toISOString === 'function') {
      try {
        return candidate.toISOString();
      } catch {
        // ignore and continue to fallback parsing
      }
    }

    if (typeof candidate.valueOf === 'function') {
      const ts = candidate.valueOf();
      if (typeof ts === 'number' && !Number.isNaN(ts)) {
        const date = new Date(ts);
        return Number.isNaN(date.getTime()) ? null : date.toISOString();
      }
    }
  }

  if (typeof value === 'string') {
    const normalized = value.includes('T') ? value : value.replace(' ', 'T');
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? value : date.toISOString();
  }

  return null;
};

const buildSubmitPayload = (): TaskFormData => ({
  ...form,
  once_datetime: normalizeOnceDateTime(form.once_datetime),
});

const extractErrorMessage = (error: any): string => {
  const responseData = error.response?.data;
  if (responseData?.errors && typeof responseData.errors === 'object') {
    const firstFieldError = Object.values(responseData.errors)
      .flat()
      .find((item) => typeof item === 'string');
    if (typeof firstFieldError === 'string') {
      return firstFieldError;
    }
  }

  return responseData?.detail || responseData?.error || responseData?.message || '操作失败';
};

const openCaseSelectModal = () => {
  caseSelectModal.value?.open(form.ui_testcase_ids);
};

const openApiCaseSelectModal = () => {
  apiCaseSelectModal.value?.open(form.api_testcase_ids);
};

const onCaseSelected = (ids: number[]) => {
  form.ui_testcase_ids = ids;
};

const onApiCaseSelected = (ids: number[]) => {
  form.api_testcase_ids = ids;
};

const missingSelectedSuiteLabel = computed(() => {
  if (!form.test_suite) return '';
  const matched = testSuites.value.find((suite) => suite.id === form.test_suite);
  if (matched) return '';
  return editingTaskMeta.value?.test_suite_name || `测试套件 #${form.test_suite}`;
});

const open = async (task?: ScheduledTask) => {
  resetForm();
  editingTaskMeta.value = task || null;

  if (task) {
    isEditing.value = true;
    editingId.value = task.id;
    Object.assign(form, {
      name: task.name,
      description: task.description,
      module: task.module,
      execution_target: task.execution_target,
      schedule_type: task.schedule_type,
      once_datetime: task.once_datetime,
      daily_time: task.daily_time,
      weekly_days: task.weekly_days || [],
      weekly_time: task.weekly_time,
      hourly_minute: task.hourly_minute,
      task_timezone: task.task_timezone || 'Asia/Shanghai',
      retry_enabled: task.retry_enabled,
      retry_count: task.retry_count,
      retry_interval: task.retry_interval,
      test_suite: task.test_suite,
      ui_testcase_ids: task.ui_testcase_ids || [],
      api_testcase_ids: task.api_testcase_ids || [],
      actuator_id: task.actuator_id || '',
    });

    if (task.module === 'test_suite') {
      await loadTestSuites();
    }
    if (task.module === 'ui_automation') {
      await loadActuators();
    }
    if (task.module === 'api_automation') {
      form.execution_target = 'backend';
    }
  } else {
    isEditing.value = false;
    editingId.value = null;
    editingTaskMeta.value = null;
    if (form.module === 'test_suite') {
      await loadTestSuites();
    }
    if (form.module === 'ui_automation') {
      await loadActuators();
    }
    if (form.module === 'api_automation') {
      form.execution_target = 'backend';
    }
  }
  visible.value = true;
};

const handleSubmit = async () => {
  const errors = await formRef.value?.validate();
  if (errors) return;

  submitting.value = true;
  try {
    const payload = buildSubmitPayload();
    if (isEditing.value && editingId.value) {
      await updateTask(props.projectId, editingId.value, payload);
      Message.success('任务已更新');
    } else {
      await createTask(props.projectId, payload);
      Message.success('任务已创建并启用');
    }
    visible.value = false;
    emit('success');
  } catch (error: any) {
    const msg = extractErrorMessage(error);
    Message.error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  } finally {
    submitting.value = false;
  }
};

const handleClose = () => {
  visible.value = false;
  editingTaskMeta.value = null;
  resetForm();
};

defineExpose({ open });
</script>

<style scoped>
.form-scroll-area {
  max-height: 60vh;
  overflow-y: auto;
  padding-right: 4px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.form-row-3 {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}

.flex-1 {
  flex: 1;
}

.retry-config {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding: 12px;
  background: var(--color-fill-1);
  border-radius: 8px;
  margin-bottom: 16px;
}

.retry-config :deep(.arco-form-item) {
  margin-bottom: 0;
}

.form-scroll-area :deep(.arco-form-item) {
  margin-bottom: 12px;
}

.form-tip {
  margin: 0 0 12px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-2);
  background: var(--color-fill-1);
  border-radius: 8px;
}
</style>
