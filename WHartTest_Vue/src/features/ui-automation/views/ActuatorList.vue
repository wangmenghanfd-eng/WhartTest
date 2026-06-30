<template>
  <div class="actuator-list">
    <!-- 头部 -->
    <div class="header">
      <div class="title">
        <h3>在线执行器</h3>
        <span class="count">共 {{ actuators.length }} 个</span>
      </div>
      <div class="actions">
        <a-button @click="loadActuators" :loading="loading">
          <template #icon><icon-refresh /></template>
          刷新
        </a-button>
      </div>
    </div>

    <!-- 状态提示 -->
    <a-alert
      v-if="!loading && actuators.length === 0"
      type="warning"
      class="mb-4"
    >
      <template #title>暂无在线执行器</template>
      请先启动执行器服务：cd WHartTest_Actuator && python main.py
    </a-alert>

    <!-- 执行器表格 -->
    <a-table
      :data="actuators"
      :loading="loading"
      :pagination="false"
      stripe
    >
      <template #columns>
        <a-table-column title="状态" :width="70" align="center">
          <template #cell="{ record }">
            <div :class="['status-dot', record.is_open ? 'status-dot-online' : 'status-dot-paused']"></div>
          </template>
        </a-table-column>
        <a-table-column title="名称" data-index="name" :width="160" />
        <a-table-column title="IP地址" data-index="ip" :width="150" />
        <a-table-column title="类型" :width="100">
          <template #cell="{ record }">
            <a-tag :color="getTypeTagColor(record.type)" size="small">
              {{ getTypeLabel(record.type) }}
            </a-tag>
          </template>
        </a-table-column>
        <a-table-column title="浏览器" data-index="browser_type" :width="100" />
        <a-table-column title="OPEN" :width="80" align="center">
          <template #cell="{ record }">
            <a-switch
              v-model="record.is_open"
              size="small"
              :loading="togglingId === record.id"
              @change="(val) => handleToggleOpen(record, Boolean(val))"
            />
          </template>
        </a-table-column>
        <a-table-column title="上线时间" :width="170">
          <template #cell="{ record }">
            <span class="time-text">{{ formatTime(record.connected_at) }}</span>
          </template>
        </a-table-column>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconRefresh } from '@arco-design/web-vue/es/icon'
import { actuatorApi, type ActuatorInfo } from '../api'
import { extractResponseData } from '../types'

void IconRefresh

const actuators = ref<ActuatorInfo[]>([])
const loading = ref(false)
const togglingId = ref<string | null>(null)
let refreshTimer: ReturnType<typeof setInterval> | null = null
const REFRESH_INTERVAL_MS = 30000

const loadActuators = async () => {
  loading.value = true
  try {
    const res = await actuatorApi.list()
    // 执行器接口是双层包装({status,data:{count,items}}) + 拦截器再包一层，
    // extractResponseData 会递归解包到 {count, items}
    const payload = extractResponseData<{ count: number; items: ActuatorInfo[] }>(res)
    actuators.value = Array.isArray(payload?.items) ? payload!.items : []
  } catch (e) {
    console.error('Load actuators error:', e)
    actuators.value = []
  } finally {
    loading.value = false
  }
}

const stopRefreshTimer = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const startRefreshTimer = () => {
  stopRefreshTimer()
  if (!document.hidden) {
    refreshTimer = setInterval(loadActuators, REFRESH_INTERVAL_MS)
  }
}

const handleVisibilityChange = () => {
  if (document.hidden) {
    stopRefreshTimer()
    return
  }
  void loadActuators()
  startRefreshTimer()
}

const handleToggleOpen = async (record: ActuatorInfo, val: boolean) => {
  togglingId.value = record.id
  try {
    await actuatorApi.toggleOpen(record.id, val)
    record.is_open = val
    Message.success(val ? `执行器 ${record.name} 已开启接单` : `执行器 ${record.name} 已暂停接单`)
  } catch {
    record.is_open = !val
    Message.error('操作失败，请重试')
  } finally {
    togglingId.value = null
  }
}

const getTypeLabel = (type: string) => {
  const typeMap: Record<string, string> = {
    web_ui: 'Web UI',
    android_ui: 'Android UI',
    pytest: 'Pytest',
    pytest_web: 'Pytest Web',
  }
  return typeMap[type] || type
}

const getTypeTagColor = (type: string) => {
  const typeMap: Record<string, string> = {
    web_ui: 'arcoblue',
    android_ui: 'green',
    pytest: 'orangered',
    pytest_web: 'purple',
  }
  return typeMap[type] || 'gray'
}

const formatTime = (isoString: string) => {
  if (!isoString) return '-'
  const date = new Date(isoString)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const refresh = () => loadActuators()

defineExpose({ refresh })

onMounted(() => {
  void loadActuators()
  startRefreshTimer()
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  stopRefreshTimer()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<style scoped lang="scss">
.actuator-list {
  padding: 16px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;

  .title {
    display: flex;
    align-items: center;
    gap: 12px;

    h3 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
    }

    .count {
      color: var(--color-text-3);
      font-size: 14px;
    }
  }
}

.mb-4 {
  margin-bottom: 16px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}

.status-dot-online {
  background: #00b42a;
  box-shadow: 0 0 8px rgba(0, 180, 42, 0.5);
}

.status-dot-paused {
  background: #ffb400;
  box-shadow: 0 0 8px rgba(255, 180, 0, 0.5);
}

.time-text {
  font-size: 12px;
  color: var(--color-text-3);
}
</style>
