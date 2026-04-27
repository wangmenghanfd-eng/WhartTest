<template>
  <div class="api-automation-layout">
    <aside class="module-panel">
      <div class="panel-title">接口项目/模块</div>
      <a-button type="primary" size="small" long @click="openModuleModal()">新增模块</a-button>
      <a-tree
        class="module-tree"
        :data="moduleTree"
        :field-names="{ key: 'id', title: 'name', children: 'children' }"
        block-node
        @select="onModuleSelect"
      />
    </aside>

    <section class="layout-content">
      <a-tabs v-model:active-key="activeTab" type="card-gutter">
        <a-tab-pane key="definitions" title="接口定义">
          <div class="toolbar">
            <a-input-search v-model="definitionSearch" placeholder="搜索接口名称/路径" allow-clear @search="fetchDefinitions" @clear="fetchDefinitions" />
            <a-button type="primary" @click="importModalVisible = true">OpenAPI/Swagger 导入</a-button>
          </div>
          <a-table :columns="definitionColumns" :data="definitions" :loading="loading" :pagination="false" :scroll="{ x: 900 }">
            <template #method="{ record }"><a-tag color="arcoblue">{{ record.method }}</a-tag></template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="cases" title="接口用例">
          <div class="toolbar">
            <a-input-search v-model="caseSearch" placeholder="搜索用例名称/路径" allow-clear @search="fetchCases" @clear="fetchCases" />
            <a-select v-model="selectedEnvId" placeholder="执行环境" allow-clear style="width: 220px">
              <a-option v-for="env in envConfigs" :key="env.id" :value="env.id">{{ env.name }}</a-option>
            </a-select>
            <a-button @click="handleGenerateFromTrace">UI Trace 转接口用例</a-button>
            <a-button @click="handleGenerateFromFunctional">功能用例转接口用例</a-button>
            <a-button type="primary" @click="openCaseModal()">新增用例</a-button>
            <a-button type="outline" :disabled="!selectedCaseIds.length" @click="batchExecute">批量执行</a-button>
          </div>
          <a-table
            row-key="id"
            :row-selection="{ type: 'checkbox', showCheckedAll: true }"
            v-model:selected-keys="selectedCaseIds"
            :columns="caseColumns"
            :data="cases"
            :loading="loading"
            :pagination="false"
            :scroll="{ x: 1100 }"
          >
            <template #method="{ record }"><a-tag color="arcoblue">{{ record.method }}</a-tag></template>
            <template #status="{ record }"><a-tag :color="record.status === 2 ? 'green' : record.status === 3 ? 'red' : 'gray'">{{ STATUS_LABELS[record.status] }}</a-tag></template>
            <template #case_operations="{ record }">
              <a-space>
                <a-button type="text" size="mini" @click="executeCase(record)">执行</a-button>
                <a-button type="text" size="mini" @click="enhanceCase(record)">AI增强</a-button>
              </a-space>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="scripts" title="前置/后置脚本">
          <div class="toolbar">
            <a-button type="primary" @click="openScriptModal()">新增脚本</a-button>
          </div>
          <a-table :columns="scriptColumns" :data="scripts" :loading="loading" :pagination="false">
            <template #script_type="{ record }"><a-tag>{{ record.script_type === 'pre' ? '前置' : '后置' }}</a-tag></template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="assertions" title="断言">
          <a-alert>断言随接口用例维护。V1 支持状态码、响应体包含、响应头存在；后续 AI 增强会在这里辅助补全。</a-alert>
        </a-tab-pane>

        <a-tab-pane key="extractors" title="变量提取">
          <a-alert>变量提取随接口用例维护。V1 先保留结构字段，后续会支持 JSONPath/Header 提取并写入运行上下文。</a-alert>
        </a-tab-pane>

        <a-tab-pane key="public-data" title="公共数据">
          <div class="toolbar">
            <a-input-search v-model="publicDataSearch" placeholder="搜索变量名/变量值" allow-clear @search="fetchPublicData" @clear="fetchPublicData" />
            <a-button type="primary" @click="openPublicDataModal()">新增公共数据</a-button>
          </div>
          <a-table :columns="publicDataColumns" :data="publicData" :loading="loading" :pagination="false">
            <template #enabled="{ record }"><a-tag :color="record.is_enabled ? 'green' : 'gray'">{{ record.is_enabled ? '启用' : '停用' }}</a-tag></template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="env" title="环境配置">
          <div class="toolbar">
            <a-input-search v-model="envSearch" placeholder="搜索环境名称/URL" allow-clear @search="fetchEnvConfigs" @clear="fetchEnvConfigs" />
            <a-button type="primary" @click="openEnvModal()">新增环境</a-button>
          </div>
          <a-table :columns="envColumns" :data="envConfigs" :loading="loading" :pagination="false">
            <template #default="{ record }"><a-tag v-if="record.is_default" color="green">默认</a-tag><span v-else>-</span></template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="batch" title="批量执行">
          <a-table :columns="batchColumns" :data="batches" :loading="loading" :pagination="false" :scroll="{ x: 900 }">
            <template #batch_status="{ record }"><a-tag>{{ BATCH_STATUS_LABELS[record.status] }}</a-tag></template>
            <template #rate="{ record }">{{ record.success_rate?.toFixed?.(1) ?? record.success_rate }}%</template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="records" title="执行记录">
          <a-table :columns="recordColumns" :data="records" :loading="loading" :pagination="false" :scroll="{ x: 1000 }">
            <template #record_status="{ record }"><a-tag :color="record.status === 2 ? 'green' : record.status === 3 ? 'red' : 'gray'">{{ STATUS_LABELS[record.status] }}</a-tag></template>
            <template #error="{ record }">
              <a-tooltip v-if="record.error_message" :content="record.error_message">
                <span class="ellipsis-error">{{ record.error_message }}</span>
              </a-tooltip>
              <span v-else>-</span>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="reports" title="报告">
          <a-alert>报告会复用执行记录与批量执行数据生成。V1 先在执行记录/批量执行中查看明细。</a-alert>
        </a-tab-pane>

        <a-tab-pane key="scheduled" title="定时任务">
          <a-alert>接口自动化定时任务入口已预留。下一步会接入任务中心，让接口用例批量执行可以按计划触发。</a-alert>
        </a-tab-pane>
      </a-tabs>
    </section>

    <a-modal v-model:visible="importModalVisible" title="OpenAPI/Swagger 导入" :ok-loading="submitting" @before-ok="submitOpenApiImport">
      <a-form layout="vertical">
        <a-form-item label="OpenAPI URL">
          <a-input v-model="importForm.url" placeholder="https://example.com/openapi.json" />
        </a-form-item>
        <a-form-item label="或粘贴 JSON/YAML">
          <a-textarea v-model="importForm.content" :auto-size="{ minRows: 6, maxRows: 12 }" placeholder="粘贴 OpenAPI 内容" />
        </a-form-item>
        <a-form-item label="同时生成基础接口用例">
          <a-switch v-model="importForm.create_cases" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:visible="moduleModalVisible" title="接口模块" @before-ok="submitModule">
      <a-input v-model="moduleForm.name" placeholder="模块名称" />
    </a-modal>

    <a-modal v-model:visible="envModalVisible" title="环境配置" @before-ok="submitEnv">
      <a-form layout="vertical">
        <a-form-item label="环境名称"><a-input v-model="envForm.name" /></a-form-item>
        <a-form-item label="基础 URL"><a-input v-model="envForm.base_url" placeholder="https://api.example.com" /></a-form-item>
        <a-form-item label="默认环境"><a-switch v-model="envForm.is_default" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:visible="caseModalVisible" title="接口用例" @before-ok="submitCase">
      <a-form layout="vertical">
        <a-form-item label="用例名称"><a-input v-model="caseForm.name" /></a-form-item>
        <a-form-item label="请求方法"><a-select v-model="caseForm.method"><a-option v-for="m in methods" :key="m" :value="m">{{ m }}</a-option></a-select></a-form-item>
        <a-form-item label="路径"><a-input v-model="caseForm.path" placeholder="/api/users" /></a-form-item>
        <a-form-item label="断言 JSON"><a-textarea v-model="caseAssertionsText" :auto-size="{ minRows: 3, maxRows: 6 }" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:visible="publicDataModalVisible" title="公共数据" @before-ok="submitPublicData">
      <a-form layout="vertical">
        <a-form-item label="变量名"><a-input v-model="publicDataForm.key" /></a-form-item>
        <a-form-item label="变量值"><a-textarea v-model="publicDataForm.value" /></a-form-item>
        <a-form-item label="启用"><a-switch v-model="publicDataForm.is_enabled" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:visible="scriptModalVisible" title="前置/后置脚本" @before-ok="submitScript">
      <a-form layout="vertical">
        <a-form-item label="脚本名称"><a-input v-model="scriptForm.name" /></a-form-item>
        <a-form-item label="类型"><a-select v-model="scriptForm.script_type"><a-option value="pre">前置</a-option><a-option value="post">后置</a-option></a-select></a-form-item>
        <a-form-item label="内容"><a-textarea v-model="scriptForm.content" :auto-size="{ minRows: 5, maxRows: 10 }" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { useProjectStore } from '@/store/projectStore'
import {
  apiCaseApi,
  apiDefinitionApi,
  apiEnvApi,
  apiModuleApi,
  apiPublicDataApi,
  apiRecordApi,
  apiScriptApi,
} from '../api'
import type {
  ApiBatchExecutionRecord,
  ApiDefinition,
  ApiEnvironmentConfig,
  ApiExecutionRecord,
  ApiModule,
  ApiPublicData,
  ApiScript,
  ApiTestCase,
} from '../types'
import { BATCH_STATUS_LABELS, STATUS_LABELS, unwrapData, unwrapPage } from '../types'

const projectStore = useProjectStore()
const projectId = computed(() => projectStore.currentProject?.id)
const activeTab = ref('definitions')
const loading = ref(false)
const submitting = ref(false)
const selectedModuleId = ref<number | undefined>()
const selectedEnvId = ref<number | undefined>()
const selectedCaseIds = ref<number[]>([])

const moduleTree = ref<ApiModule[]>([])
const definitions = ref<ApiDefinition[]>([])
const cases = ref<ApiTestCase[]>([])
const envConfigs = ref<ApiEnvironmentConfig[]>([])
const publicData = ref<ApiPublicData[]>([])
const scripts = ref<ApiScript[]>([])
const records = ref<ApiExecutionRecord[]>([])
const batches = ref<ApiBatchExecutionRecord[]>([])

const definitionSearch = ref('')
const caseSearch = ref('')
const envSearch = ref('')
const publicDataSearch = ref('')

const importModalVisible = ref(false)
const moduleModalVisible = ref(false)
const envModalVisible = ref(false)
const caseModalVisible = ref(false)
const publicDataModalVisible = ref(false)
const scriptModalVisible = ref(false)

const importForm = reactive({ url: '', content: '', create_cases: true })
const moduleForm = reactive({ name: '' })
const envForm = reactive({ name: '', base_url: '', is_default: false })
const caseForm = reactive({ name: '', method: 'GET', path: '' })
const caseAssertionsText = ref('[{"type":"status_code","operator":"lt","expected":500}]')
const publicDataForm = reactive({ key: '', value: '', is_enabled: true })
const scriptForm = reactive({ name: '', script_type: 'pre' as 'pre' | 'post', content: '' })
const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

const definitionColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '方法', slotName: 'method', width: 90 },
  { title: '接口名称', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '路径', dataIndex: 'path', ellipsis: true, tooltip: true },
  { title: '模块', dataIndex: 'module_name', width: 140 },
  { title: '来源', dataIndex: 'source', width: 100 },
]
const caseColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '方法', slotName: 'method', width: 90 },
  { title: '用例名称', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '路径', dataIndex: 'path', ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'status', width: 90 },
  { title: '操作', slotName: 'case_operations', width: 150, fixed: 'right' as const },
]
const envColumns = [
  { title: '环境名称', dataIndex: 'name' },
  { title: '基础 URL', dataIndex: 'base_url', ellipsis: true, tooltip: true },
  { title: '默认', slotName: 'default', width: 80 },
]
const publicDataColumns = [
  { title: '变量名', dataIndex: 'key' },
  { title: '变量值', dataIndex: 'value', ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'enabled', width: 90 },
]
const scriptColumns = [
  { title: '脚本名称', dataIndex: 'name' },
  { title: '类型', slotName: 'script_type', width: 100 },
  { title: '内容', dataIndex: 'content', ellipsis: true, tooltip: true },
]
const recordColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '用例名称', dataIndex: 'test_case_name', ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'record_status', width: 90 },
  { title: '耗时', dataIndex: 'duration', width: 90 },
  { title: '错误', slotName: 'error', width: 220 },
]
const batchColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '批次名称', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'batch_status', width: 100 },
  { title: '成功/失败/总计', render: ({ record }: { record: ApiBatchExecutionRecord }) => `${record.passed_cases}/${record.failed_cases}/${record.total_cases}` },
  { title: '成功率', slotName: 'rate', width: 90 },
]

const currentParams = () => ({ project: projectId.value, module: selectedModuleId.value })

const fetchModules = async () => {
  if (!projectId.value) return
  const res = await apiModuleApi.tree(projectId.value)
  moduleTree.value = unwrapData<ApiModule[]>(res) || []
}
const fetchDefinitions = async () => {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await apiDefinitionApi.list({ ...currentParams(), search: definitionSearch.value || undefined })
    definitions.value = unwrapPage<ApiDefinition>(res).items
  } finally {
    loading.value = false
  }
}
const fetchCases = async () => {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await apiCaseApi.list({ ...currentParams(), search: caseSearch.value || undefined })
    cases.value = unwrapPage<ApiTestCase>(res).items
  } finally {
    loading.value = false
  }
}
const fetchEnvConfigs = async () => {
  if (!projectId.value) return
  const res = await apiEnvApi.list({ project: projectId.value, search: envSearch.value || undefined })
  envConfigs.value = unwrapPage<ApiEnvironmentConfig>(res).items
}
const fetchPublicData = async () => {
  if (!projectId.value) return
  const res = await apiPublicDataApi.list({ project: projectId.value, search: publicDataSearch.value || undefined })
  publicData.value = unwrapPage<ApiPublicData>(res).items
}
const fetchScripts = async () => {
  if (!projectId.value) return
  const res = await apiScriptApi.list({ ...currentParams() })
  scripts.value = unwrapPage<ApiScript>(res).items
}
const fetchRecords = async () => {
  if (!projectId.value) return
  const [recordRes, batchRes] = await Promise.all([
    apiRecordApi.list({ project: projectId.value }),
    apiRecordApi.batches({ project: projectId.value }),
  ])
  records.value = unwrapPage<ApiExecutionRecord>(recordRes).items
  batches.value = unwrapPage<ApiBatchExecutionRecord>(batchRes).items
}
const refreshActive = () => {
  if (activeTab.value === 'definitions') fetchDefinitions()
  if (activeTab.value === 'cases') fetchCases()
  if (activeTab.value === 'env') fetchEnvConfigs()
  if (activeTab.value === 'public-data') fetchPublicData()
  if (activeTab.value === 'scripts') fetchScripts()
  if (activeTab.value === 'records' || activeTab.value === 'batch') fetchRecords()
}
const refreshAllBase = async () => {
  await Promise.all([fetchModules(), fetchEnvConfigs(), fetchDefinitions(), fetchCases(), fetchPublicData(), fetchScripts(), fetchRecords()])
}

const onModuleSelect = (keys: Array<string | number>) => {
  selectedModuleId.value = keys?.[0] ? Number(keys[0]) : undefined
  refreshActive()
}
const openModuleModal = () => { moduleForm.name = ''; moduleModalVisible.value = true }
const openEnvModal = () => { Object.assign(envForm, { name: '', base_url: '', is_default: false }); envModalVisible.value = true }
const openCaseModal = () => { Object.assign(caseForm, { name: '', method: 'GET', path: '' }); caseModalVisible.value = true }
const openPublicDataModal = () => { Object.assign(publicDataForm, { key: '', value: '', is_enabled: true }); publicDataModalVisible.value = true }
const openScriptModal = () => { Object.assign(scriptForm, { name: '', script_type: 'pre', content: '' }); scriptModalVisible.value = true }

const submitOpenApiImport = async (done: (closed: boolean) => void) => {
  if (!projectId.value) return done(false)
  submitting.value = true
  try {
    const res = await apiDefinitionApi.importOpenApi({ ...importForm, project: projectId.value })
    const data = unwrapData<any>(res)
    Message.success(`导入完成：新增 ${data.created_definitions}，更新 ${data.updated_definitions}，生成用例 ${data.created_cases}`)
    done(true)
    await refreshAllBase()
  } catch (err: any) {
    Message.error(err?.error || '导入失败')
    done(false)
  } finally {
    submitting.value = false
  }
}
const submitModule = async (done: (closed: boolean) => void) => {
  if (!projectId.value || !moduleForm.name) return done(false)
  await apiModuleApi.create({ project: projectId.value, name: moduleForm.name, parent: selectedModuleId.value ?? null })
  Message.success('模块已创建')
  done(true)
  fetchModules()
}
const submitEnv = async (done: (closed: boolean) => void) => {
  if (!projectId.value || !envForm.name) return done(false)
  await apiEnvApi.create({ project: projectId.value, ...envForm })
  Message.success('环境已创建')
  done(true)
  fetchEnvConfigs()
}
const submitCase = async (done: (closed: boolean) => void) => {
  if (!projectId.value || !selectedModuleId.value || !caseForm.name || !caseForm.path) {
    Message.warning('请先选择模块，并填写用例名称和路径')
    return done(false)
  }
  let assertions
  try {
    assertions = JSON.parse(caseAssertionsText.value || '[]')
  } catch {
    Message.warning('断言 JSON 格式不正确')
    return done(false)
  }
  await apiCaseApi.create({ project: projectId.value, module: selectedModuleId.value, ...caseForm, environment: selectedEnvId.value, assertions })
  Message.success('用例已创建')
  done(true)
  fetchCases()
}
const submitPublicData = async (done: (closed: boolean) => void) => {
  if (!projectId.value || !publicDataForm.key) return done(false)
  await apiPublicDataApi.create({ project: projectId.value, ...publicDataForm })
  Message.success('公共数据已创建')
  done(true)
  fetchPublicData()
}
const submitScript = async (done: (closed: boolean) => void) => {
  if (!projectId.value || !scriptForm.name) return done(false)
  await apiScriptApi.create({ project: projectId.value, module: selectedModuleId.value, ...scriptForm })
  Message.success('脚本已创建')
  done(true)
  fetchScripts()
}
const executeCase = async (record: ApiTestCase) => {
  await apiCaseApi.execute(record.id, { environment: selectedEnvId.value })
  Message.success('已提交执行')
  setTimeout(fetchRecords, 1200)
}
const batchExecute = async () => {
  if (!projectId.value || !selectedCaseIds.value.length) return
  await apiCaseApi.batchExecute({ project: projectId.value, case_ids: selectedCaseIds.value, environment: selectedEnvId.value })
  Message.success('批量执行已提交')
  setTimeout(fetchRecords, 1500)
}
const enhanceCase = async (record: ApiTestCase) => {
  const res = await apiCaseApi.aiEnhance(record.id)
  Message.info(unwrapData<any>(res)?.message || 'AI增强入口已预留')
}
const handleGenerateFromTrace = async () => {
  const res = await apiCaseApi.generateFromUiTrace({ project: projectId.value })
  Message.info(unwrapData<any>(res)?.message || '入口已预留')
}
const handleGenerateFromFunctional = async () => {
  const res = await apiCaseApi.generateFromFunctionalCase({ project: projectId.value })
  Message.info(unwrapData<any>(res)?.message || '入口已预留')
}

watch(projectId, () => {
  selectedModuleId.value = undefined
  if (projectId.value) refreshAllBase()
}, { immediate: true })
watch(activeTab, refreshActive)
</script>

<style scoped>
.api-automation-layout {
  display: flex;
  gap: 10px;
  height: 100%;
  overflow: hidden;
}
.module-panel {
  width: 220px;
  flex: 0 0 220px;
  padding: 16px;
  background: var(--color-bg-2);
  border-radius: 8px;
  overflow: auto;
}
.panel-title {
  font-weight: 600;
  margin-bottom: 12px;
}
.module-tree {
  margin-top: 12px;
}
.layout-content {
  flex: 1;
  min-width: 0;
  padding: 20px;
  background: #fff;
  border-radius: 8px;
  overflow: auto;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}
.toolbar :deep(.arco-input-wrapper) {
  max-width: 260px;
}
.ellipsis-error {
  display: inline-block;
  max-width: 210px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgb(var(--red-6));
  vertical-align: bottom;
}
@media (max-width: 900px) {
  .api-automation-layout {
    flex-direction: column;
  }
  .module-panel {
    width: 100%;
    flex-basis: auto;
    max-height: 220px;
  }
}
</style>
