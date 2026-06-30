<template>
  <div class="api-automation-layout">
    <aside class="module-panel">
      <div class="panel-title">接口项目/模块</div>
      <a-button type="primary" size="small" long @click="openModuleModal()">新增根模块</a-button>
      <a-tree
        class="module-tree"
        :data="moduleTree"
        :field-names="{ key: 'id', title: 'name', children: 'children' }"
        block-node
        @select="onModuleSelect"
      >
        <template #title="node">
          <div class="module-node">
            <span class="module-node-name">{{ node.name }}</span>
            <a-dropdown trigger="hover" @select="(v) => handleModuleAction(String(v), node)">
              <a-button type="text" size="mini" class="module-node-more" @click.stop>···</a-button>
              <template #content>
                <a-doption value="addChild">添加子模块</a-doption>
                <a-doption value="edit">编辑模块</a-doption>
                <a-doption value="delete">删除模块</a-doption>
              </template>
            </a-dropdown>
          </div>
        </template>
      </a-tree>
    </aside>

    <section class="layout-content">
      <a-tabs v-model:active-key="activeTab" type="card-gutter">
        <a-tab-pane key="definitions" title="接口定义">
          <div class="toolbar">
            <a-input-search v-model="definitionSearch" placeholder="搜索接口名称/路径" allow-clear @search="fetchDefinitions" @clear="fetchDefinitions" />
            <a-button type="primary" @click="importModalVisible = true">OpenAPI/Swagger 导入</a-button>
            <a-button @click="openDefinitionModal()">手动新增接口</a-button>
          </div>
          <a-table :columns="definitionColumns" :data="definitions" :loading="loading" :pagination="false" :scroll="{ x: 1100 }">
            <template #method="{ record }"><a-tag color="arcoblue">{{ record.method }}</a-tag></template>
            <template #def_ops="{ record }">
              <a-space size="mini">
                <a-button type="text" size="mini" @click="handleGenerateCaseFromDefinition(record)">生成用例</a-button>
                <a-button type="text" size="mini" @click="openDefinitionModal(record)">编辑</a-button>
                <a-popconfirm content="确认删除该接口定义？已关联的用例将保留。" @ok="handleDeleteDefinition(record)">
                  <a-button type="text" size="mini" status="danger">删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
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
            <a-popconfirm content="将对选中用例调用 LLM 补全断言/提取器并直接合并写回,确认?" @ok="batchAiEnhanceCases">
              <a-button type="outline" :disabled="!selectedCaseIds.length" :loading="batchAiEnhancing">批量AI增强</a-button>
            </a-popconfirm>
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
              <a-space size="mini">
                <a-button type="text" size="mini" @click="executeCase(record)">执行</a-button>
                <a-button type="text" size="mini" @click="openCaseModal(record)">编辑</a-button>
                <a-button type="text" size="mini" @click="enhanceCase(record)">AI增强</a-button>
                <a-popconfirm content="确认删除该用例？" @ok="handleDeleteCase(record)">
                  <a-button type="text" size="mini" status="danger">删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="scripts" title="前置/后置脚本">
          <div class="toolbar">
            <a-button type="primary" @click="openScriptModal()">新增脚本</a-button>
          </div>
          <a-table :columns="scriptColumns" :data="scripts" :loading="loading" :pagination="false" :scroll="{ x: 900 }">
            <template #script_type="{ record }"><a-tag>{{ record.script_type === 'pre' ? '前置' : '后置' }}</a-tag></template>
            <template #script_ops="{ record }">
              <a-space size="mini">
                <a-button type="text" size="mini" @click="openScriptModal(record)">编辑</a-button>
                <a-popconfirm content="确认删除该脚本？" @ok="handleDeleteScript(record)">
                  <a-button type="text" size="mini" status="danger">删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="public-data" title="公共数据">
          <div class="toolbar">
            <a-input-search v-model="publicDataSearch" placeholder="搜索变量名/变量值" allow-clear @search="fetchPublicData" @clear="fetchPublicData" />
            <a-button type="primary" @click="openPublicDataModal()">新增公共数据</a-button>
          </div>
          <a-table :columns="publicDataColumns" :data="publicData" :loading="loading" :pagination="false" :scroll="{ x: 800 }">
            <template #enabled="{ record }"><a-tag :color="record.is_enabled ? 'green' : 'gray'">{{ record.is_enabled ? '启用' : '停用' }}</a-tag></template>
            <template #pd_ops="{ record }">
              <a-space size="mini">
                <a-button type="text" size="mini" @click="openPublicDataModal(record)">编辑</a-button>
                <a-popconfirm content="确认删除该公共数据？" @ok="handleDeletePublicData(record)">
                  <a-button type="text" size="mini" status="danger">删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="env" title="环境配置">
          <div class="toolbar">
            <a-input-search v-model="envSearch" placeholder="搜索环境名称/URL" allow-clear @search="fetchEnvConfigs" @clear="fetchEnvConfigs" />
            <a-button type="primary" @click="openEnvModal()">新增环境</a-button>
          </div>
          <a-table :columns="envColumns" :data="envConfigs" :loading="loading" :pagination="false" :scroll="{ x: 900 }">
            <template #is_default_cell="{ record }"><a-tag v-if="record.is_default" color="green">默认</a-tag><span v-else>-</span></template>
            <template #env_ops="{ record }">
              <a-space size="mini">
                <a-button type="text" size="mini" @click="openEnvModal(record)">编辑</a-button>
                <a-popconfirm content="确认删除该环境？" @ok="handleDeleteEnv(record)">
                  <a-button type="text" size="mini" status="danger">删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
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

        <a-tab-pane key="scenarios" title="接口场景">
          <ApiAutomationScenarios
            :project-id="projectId"
            :selected-module-id="selectedModuleId"
            :module-options="flatModuleOptions"
            :env-configs="envConfigs"
          />
        </a-tab-pane>

        <a-tab-pane key="reports" title="报告">
          <ApiAutomationReports :project-id="projectId" :reload-key="reportsReloadKey" />
        </a-tab-pane>

        <a-tab-pane key="scheduled" title="定时任务">
          <ApiAutomationScheduledTasks :project-id="projectId" :reload-key="scheduledReloadKey" />
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

    <a-modal v-model:visible="moduleModalVisible" :title="moduleModalTitle" @before-ok="submitModule">
      <a-input v-model="moduleForm.name" placeholder="模块名称" />
    </a-modal>

    <a-modal v-model:visible="envModalVisible" :title="editingEnvId ? '编辑环境' : '新增环境'" :width="640" @before-ok="submitEnv">
      <a-form layout="vertical">
        <a-form-item label="环境名称" required><a-input v-model="envForm.name" /></a-form-item>
        <a-form-item label="基础 URL" required><a-input v-model="envForm.base_url" placeholder="https://api.example.com" /></a-form-item>
        <a-form-item label="默认环境"><a-switch v-model="envForm.is_default" /></a-form-item>
        <a-form-item label="Headers（JSON）" extra="可选。会被所有请求默认使用，用例 headers 会覆盖同名项。">
          <a-textarea v-model="envForm.headersText" :auto-size="{ minRows: 3, maxRows: 8 }" placeholder='{"User-Agent": "WHartTest"}' />
        </a-form-item>
        <a-form-item label="环境变量（JSON）" extra="可选。可在请求 path/headers/body 里用 ${{ key }} 引用。">
          <a-textarea v-model="envForm.variablesText" :auto-size="{ minRows: 3, maxRows: 8 }" placeholder='{"site": "jsonplaceholder"}' />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:visible="caseModalVisible" :title="editingCaseId ? '编辑接口用例' : '新增接口用例'" :width="720" @before-ok="submitCase">
      <a-form layout="vertical">
        <a-form-item label="用例名称"><a-input v-model="caseForm.name" /></a-form-item>
        <a-form-item label="请求方法">
          <a-select v-model="caseForm.method">
            <a-option v-for="m in methods" :key="m" :value="m">{{ m }}</a-option>
          </a-select>
        </a-form-item>
        <a-form-item label="路径">
          <a-input v-model="caseForm.path" placeholder="/api/users" />
        </a-form-item>
        <a-form-item label="断言">
          <AssertionEditor v-model="caseAssertions" />
        </a-form-item>
        <a-form-item label="变量提取">
          <ExtractorEditor v-model="caseExtractors" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:visible="publicDataModalVisible" :title="editingPublicDataId ? '编辑公共数据' : '新增公共数据'" @before-ok="submitPublicData">
      <a-form layout="vertical">
        <a-form-item label="变量名"><a-input v-model="publicDataForm.key" /></a-form-item>
        <a-form-item label="变量值"><a-textarea v-model="publicDataForm.value" /></a-form-item>
        <a-form-item label="启用"><a-switch v-model="publicDataForm.is_enabled" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:visible="scriptModalVisible" :title="editingScriptId ? '编辑脚本' : '新增脚本'" :width="640" @before-ok="submitScript">
      <a-form layout="vertical">
        <a-form-item label="脚本名称" required><a-input v-model="scriptForm.name" /></a-form-item>
        <a-form-item label="所属模块" extra="不选则为项目级脚本。">
          <a-select v-model="scriptForm.module" :options="flatModuleOptions" allow-clear placeholder="项目级脚本" />
        </a-form-item>
        <a-form-item label="类型"><a-select v-model="scriptForm.script_type"><a-option value="pre">前置</a-option><a-option value="post">后置</a-option></a-select></a-form-item>
        <a-form-item label="内容"><a-textarea v-model="scriptForm.content" :auto-size="{ minRows: 5, maxRows: 12 }" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:visible="definitionModalVisible" :title="editingDefinitionId ? '编辑接口定义' : '手动新增接口定义'" :width="640" @before-ok="submitDefinition">
      <a-form layout="vertical">
        <a-form-item label="接口名称" required><a-input v-model="defForm.name" /></a-form-item>
        <a-form-item label="模块" required>
          <a-select v-model="defForm.module" :options="flatModuleOptions" allow-search placeholder="选择模块" />
        </a-form-item>
        <a-form-item label="请求方法">
          <a-select v-model="defForm.method">
            <a-option v-for="m in methods" :key="m" :value="m">{{ m }}</a-option>
          </a-select>
        </a-form-item>
        <a-form-item label="路径" required><a-input v-model="defForm.path" placeholder="/api/users" /></a-form-item>
        <a-form-item label="摘要"><a-input v-model="defForm.summary" /></a-form-item>
        <a-form-item label="标签（逗号分隔）"><a-input v-model="defForm.tagsText" placeholder="users,auth" /></a-form-item>
      </a-form>
    </a-modal>

    <TraceImportModal
      v-model:visible="traceImportVisible"
      :project-id="projectId"
      :module-options="flatModuleOptions"
      :default-module-id="selectedModuleId"
      @imported="onTraceImported"
    />

    <FunctionalCaseAiModal
      v-model:visible="functionalAiVisible"
      :project-id="projectId"
      :module-options="flatModuleOptions"
      :default-module-id="selectedModuleId"
      @imported="onTraceImported"
    />

    <AiEnhanceDrawer
      ref="aiEnhanceDrawerRef"
      v-model:visible="aiDrawerVisible"
      :case-id="aiDrawerCaseId"
      :case-name="aiDrawerCaseName"
      @applied="fetchCases"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
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
import AssertionEditor from '../components/AssertionEditor.vue'
import ExtractorEditor from '../components/ExtractorEditor.vue'
import TraceImportModal from '../components/TraceImportModal.vue'
import FunctionalCaseAiModal from '../components/FunctionalCaseAiModal.vue'
import AiEnhanceDrawer from '../components/AiEnhanceDrawer.vue'
import ApiAutomationReports from '../components/ApiAutomationReports.vue'
import ApiAutomationScenarios from '../components/ApiAutomationScenarios.vue'
import ApiAutomationScheduledTasks from '../components/ApiAutomationScheduledTasks.vue'
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
const editingModuleId = ref<number | null>(null)
const moduleParentId = ref<number | null>(null)
const moduleModalTitle = computed(() =>
  editingModuleId.value ? '编辑模块' : moduleParentId.value ? '新增子模块' : '新增根模块'
)
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
const definitionModalVisible = ref(false)
const traceImportVisible = ref(false)
const functionalAiVisible = ref(false)

const editingDefinitionId = ref<number | null>(null)
const editingCaseId = ref<number | null>(null)
const editingEnvId = ref<number | null>(null)
const editingScriptId = ref<number | null>(null)
const editingPublicDataId = ref<number | null>(null)

const aiDrawerVisible = ref(false)
const aiDrawerCaseId = ref<number | null>(null)
const aiDrawerCaseName = ref<string>('')
const aiEnhanceDrawerRef = ref<InstanceType<typeof AiEnhanceDrawer> | null>(null)

const reportsReloadKey = ref(0)
const scheduledReloadKey = ref(0)

const flatModuleOptions = computed<{ label: string; value: number }[]>(() => {
  const result: { label: string; value: number }[] = []
  const walk = (nodes: ApiModule[], prefix = '') => {
    for (const node of nodes) {
      const label = `${prefix}${node.name}`
      result.push({ label, value: node.id })
      const children = (node as any).children as ApiModule[] | undefined
      if (children?.length) walk(children, `${label} / `)
    }
  }
  walk(moduleTree.value)
  return result
})

const importForm = reactive({ url: '', content: '', create_cases: true })
const moduleForm = reactive({ name: '' })
const envForm = reactive({
  name: '',
  base_url: '',
  is_default: false,
  headersText: '',
  variablesText: '',
})
const caseForm = reactive({ name: '', method: 'GET', path: '', module: undefined as number | undefined })
const caseAssertions = ref<Array<Record<string, any>>>([
  { type: 'status_code', operator: 'lt', expected: 500 },
])
const caseExtractors = ref<Array<Record<string, any>>>([])
const publicDataForm = reactive({ key: '', value: '', is_enabled: true })
const scriptForm = reactive({
  name: '',
  script_type: 'pre' as 'pre' | 'post',
  content: '',
  module: undefined as number | undefined,
})
const defForm = reactive({
  name: '',
  module: undefined as number | undefined,
  method: 'GET',
  path: '',
  summary: '',
  tagsText: '',
})
const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']

const definitionColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '方法', slotName: 'method', width: 90 },
  { title: '接口名称', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '路径', dataIndex: 'path', ellipsis: true, tooltip: true },
  { title: '模块', dataIndex: 'module_name', width: 140 },
  { title: '来源', dataIndex: 'source', width: 100 },
  { title: '操作', slotName: 'def_ops', width: 220, fixed: 'right' as const },
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
  { title: '默认', slotName: 'is_default_cell', width: 80 },
  { title: '操作', slotName: 'env_ops', width: 160, fixed: 'right' as const },
]
const publicDataColumns = [
  { title: '变量名', dataIndex: 'key' },
  { title: '变量值', dataIndex: 'value', ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'enabled', width: 90 },
  { title: '操作', slotName: 'pd_ops', width: 160, fixed: 'right' as const },
]
const scriptColumns = [
  { title: '脚本名称', dataIndex: 'name' },
  { title: '类型', slotName: 'script_type', width: 100 },
  { title: '模块', dataIndex: 'module_name', width: 160 },
  { title: '内容', dataIndex: 'content', ellipsis: true, tooltip: true },
  { title: '操作', slotName: 'script_ops', width: 160, fixed: 'right' as const },
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
  { title: '成功/失败/总计', render: (data?: { record?: ApiBatchExecutionRecord }) => { const r = data?.record; return r ? `${r.passed_cases}/${r.failed_cases}/${r.total_cases}` : '-' } },
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
const openModuleModal = () => {
  if (!projectId.value) { Message.warning('请先在顶部选择一个项目'); return }
  editingModuleId.value = null
  moduleParentId.value = null
  moduleForm.name = ''
  moduleModalVisible.value = true
}

const handleModuleAction = (action: string, node: ApiModule) => {
  if (action === 'addChild') {
    editingModuleId.value = null
    moduleParentId.value = node.id
    moduleForm.name = ''
    moduleModalVisible.value = true
  } else if (action === 'edit') {
    editingModuleId.value = node.id
    moduleParentId.value = null
    moduleForm.name = node.name
    moduleModalVisible.value = true
  } else if (action === 'delete') {
    Modal.warning({
      title: '删除模块',
      content: `确认删除模块「${node.name}」？该模块下的子模块/用例可能一并受影响。`,
      hideCancel: false,
      onOk: async () => {
        try {
          await apiModuleApi.delete(node.id)
          Message.success('删除成功')
          if (selectedModuleId.value === node.id) { selectedModuleId.value = undefined; refreshActive() }
          fetchModules()
        } catch (e: any) {
          Message.error(e?.response?.data?.message || '删除失败，请检查该模块下是否仍有用例')
        }
      },
    })
  }
}

const openEnvModal = (record?: ApiEnvironmentConfig) => {
  if (record) {
    editingEnvId.value = record.id
    Object.assign(envForm, {
      name: record.name,
      base_url: record.base_url,
      is_default: !!record.is_default,
      headersText: record.headers ? JSON.stringify(record.headers, null, 2) : '',
      variablesText: record.variables ? JSON.stringify(record.variables, null, 2) : '',
    })
  } else {
    editingEnvId.value = null
    Object.assign(envForm, { name: '', base_url: '', is_default: false, headersText: '', variablesText: '' })
  }
  envModalVisible.value = true
}

const openCaseModal = (record?: ApiTestCase) => {
  if (record) {
    editingCaseId.value = record.id
    Object.assign(caseForm, {
      name: record.name,
      method: record.method,
      path: record.path,
      module: record.module,
    })
    caseAssertions.value = Array.isArray(record.assertions) && record.assertions.length
      ? (record.assertions as Array<Record<string, any>>).map((it) => ({ ...it }))
      : [{ type: 'status_code', operator: 'lt', expected: 500 }]
    caseExtractors.value = Array.isArray(record.extractors)
      ? (record.extractors as Array<Record<string, any>>).map((it) => ({ ...it }))
      : []
  } else {
    editingCaseId.value = null
    Object.assign(caseForm, { name: '', method: 'GET', path: '', module: selectedModuleId.value })
    caseAssertions.value = [{ type: 'status_code', operator: 'lt', expected: 500 }]
    caseExtractors.value = []
  }
  caseModalVisible.value = true
}

const openPublicDataModal = (record?: ApiPublicData) => {
  if (record) {
    editingPublicDataId.value = record.id
    Object.assign(publicDataForm, { key: record.key, value: record.value, is_enabled: !!record.is_enabled })
  } else {
    editingPublicDataId.value = null
    Object.assign(publicDataForm, { key: '', value: '', is_enabled: true })
  }
  publicDataModalVisible.value = true
}

const openScriptModal = (record?: ApiScript) => {
  if (record) {
    editingScriptId.value = record.id
    Object.assign(scriptForm, {
      name: record.name,
      script_type: record.script_type,
      content: record.content || '',
      module: record.module,
    })
  } else {
    editingScriptId.value = null
    Object.assign(scriptForm, { name: '', script_type: 'pre', content: '', module: selectedModuleId.value })
  }
  scriptModalVisible.value = true
}

const openDefinitionModal = (record?: ApiDefinition) => {
  if (record) {
    editingDefinitionId.value = record.id
    Object.assign(defForm, {
      name: record.name,
      module: record.module,
      method: record.method,
      path: record.path,
      summary: record.summary || '',
      tagsText: Array.isArray(record.tags) ? record.tags.join(',') : '',
    })
  } else {
    editingDefinitionId.value = null
    Object.assign(defForm, { name: '', module: selectedModuleId.value, method: 'GET', path: '', summary: '', tagsText: '' })
  }
  definitionModalVisible.value = true
}

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
  if (!projectId.value || !moduleForm.name.trim()) return done(false)
  try {
    if (editingModuleId.value) {
      await apiModuleApi.update(editingModuleId.value, { name: moduleForm.name.trim() })
      Message.success('模块已更新')
    } else {
      await apiModuleApi.create({ project: projectId.value, name: moduleForm.name.trim(), parent: moduleParentId.value })
      Message.success('模块已创建')
    }
    done(true)
    fetchModules()
  } catch (e: any) {
    Message.error(e?.response?.data?.message || '操作失败')
    done(false)
  }
}
function tryParseJsonObj(text: string): { ok: boolean; data?: Record<string, unknown>; error?: string } {
  const t = (text || '').trim()
  if (!t) return { ok: true, data: {} }
  try {
    const obj = JSON.parse(t)
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) return { ok: true, data: obj as Record<string, unknown> }
    return { ok: false, error: '请填写 JSON 对象' }
  } catch (e: any) {
    return { ok: false, error: e?.message || 'JSON 格式错误' }
  }
}

const submitEnv = async (done: (closed: boolean) => void) => {
  if (!projectId.value || !envForm.name || !envForm.base_url) {
    Message.warning('请填写环境名称和基础 URL')
    return done(false)
  }
  const headersResult = tryParseJsonObj(envForm.headersText)
  if (!headersResult.ok) {
    Message.error('Headers 解析失败：' + headersResult.error)
    return done(false)
  }
  const variablesResult = tryParseJsonObj(envForm.variablesText)
  if (!variablesResult.ok) {
    Message.error('环境变量解析失败：' + variablesResult.error)
    return done(false)
  }
  const payload: Record<string, unknown> = {
    project: projectId.value,
    name: envForm.name,
    base_url: envForm.base_url,
    is_default: envForm.is_default,
    headers: headersResult.data,
    variables: variablesResult.data,
  }
  try {
    if (editingEnvId.value) {
      await apiEnvApi.update(editingEnvId.value, payload)
      Message.success('环境已更新')
    } else {
      await apiEnvApi.create(payload)
      Message.success('环境已创建')
    }
    done(true)
    fetchEnvConfigs()
  } catch (err: any) {
    Message.error(err?.error || '保存失败')
    done(false)
  }
}

const submitCase = async (done: (closed: boolean) => void) => {
  const moduleId = caseForm.module ?? selectedModuleId.value
  if (!projectId.value || !moduleId || !caseForm.name || !caseForm.path) {
    Message.warning('请选择模块，并填写用例名称和路径')
    return done(false)
  }
  const assertions = caseAssertions.value
    .filter((it) => it && it.type)
    .map((it) => ({ ...it }))
  const extractors = caseExtractors.value
    .filter((it) => it && (it.name || '').trim())
    .map((it) => ({ ...it }))
  const payload = {
    project: projectId.value,
    module: moduleId,
    name: caseForm.name,
    method: caseForm.method,
    path: caseForm.path,
    environment: selectedEnvId.value,
    assertions,
    extractors,
  }
  try {
    if (editingCaseId.value) {
      await apiCaseApi.update(editingCaseId.value, payload)
      Message.success('用例已更新')
    } else {
      await apiCaseApi.create(payload)
      Message.success('用例已创建')
    }
    done(true)
    fetchCases()
  } catch (err: any) {
    Message.error(err?.error || '保存失败')
    done(false)
  }
}

const submitPublicData = async (done: (closed: boolean) => void) => {
  if (!projectId.value || !publicDataForm.key) return done(false)
  try {
    if (editingPublicDataId.value) {
      await apiPublicDataApi.update(editingPublicDataId.value, { ...publicDataForm })
      Message.success('公共数据已更新')
    } else {
      await apiPublicDataApi.create({ project: projectId.value, ...publicDataForm })
      Message.success('公共数据已创建')
    }
    done(true)
    fetchPublicData()
  } catch (err: any) {
    Message.error(err?.error || '保存失败')
    done(false)
  }
}

const submitScript = async (done: (closed: boolean) => void) => {
  if (!projectId.value || !scriptForm.name) return done(false)
  const payload = {
    project: projectId.value,
    module: scriptForm.module ?? null,
    name: scriptForm.name,
    script_type: scriptForm.script_type,
    content: scriptForm.content,
  }
  try {
    if (editingScriptId.value) {
      await apiScriptApi.update(editingScriptId.value, payload)
      Message.success('脚本已更新')
    } else {
      await apiScriptApi.create(payload)
      Message.success('脚本已创建')
    }
    done(true)
    fetchScripts()
  } catch (err: any) {
    Message.error(err?.error || '保存失败')
    done(false)
  }
}

const submitDefinition = async (done: (closed: boolean) => void) => {
  if (!projectId.value || !defForm.name || !defForm.module || !defForm.path) {
    Message.warning('请完善接口名称、模块、路径')
    return done(false)
  }
  const tags = defForm.tagsText
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  const payload = {
    project: projectId.value,
    module: defForm.module,
    name: defForm.name,
    method: defForm.method,
    path: defForm.path,
    summary: defForm.summary,
    tags,
    source: 'manual',
  }
  try {
    if (editingDefinitionId.value) {
      await apiDefinitionApi.update(editingDefinitionId.value, payload)
      Message.success('接口定义已更新')
    } else {
      await apiDefinitionApi.create(payload)
      Message.success('接口定义已创建')
    }
    done(true)
    fetchDefinitions()
  } catch (err: any) {
    Message.error(err?.error || '保存失败')
    done(false)
  }
}

const executeCase = async (record: ApiTestCase) => {
  const msgId = `exec-${record.id}-${Date.now()}`
  Message.loading({ id: msgId, content: `正在执行 "${record.name}"...`, duration: 0 })
  try {
    const res = await apiCaseApi.execute(record.id, { environment: selectedEnvId.value })
    const data = unwrapData<any>(res) || {}
    const recordId = data?.record_id
    // 执行接口是异步的，只返回 record_id；轮询执行记录直到出结果，再据实提示通过/失败
    let rec: any = null
    if (recordId) {
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 1500))
        try {
          rec = unwrapData<any>(await apiRecordApi.getRecord(recordId))
        } catch { /* 继续轮询 */ }
        if (rec && (rec.status === 2 || rec.status === 3)) break
      }
    } else {
      rec = data // 兼容旧的同步返回
    }
    if (rec?.status === 2) {
      const dur = typeof rec?.duration === 'number' ? `（耗时 ${rec.duration.toFixed(2)} s）` : ''
      Message.success({ id: msgId, content: `执行通过${dur}`, duration: 3000 })
    } else if (rec?.status === 3) {
      Message.error({ id: msgId, content: `执行未通过：${rec?.error_message || '断言失败'}`, duration: 4000 })
    } else {
      Message.warning({ id: msgId, content: '已提交执行，结果待定，请到“执行记录”查看', duration: 3500 })
    }
  } catch (err: any) {
    Message.error({ id: msgId, content: err?.error || '执行失败', duration: 4000 })
  } finally {
    fetchRecords()
    reportsReloadKey.value += 1
  }
}
const batchExecute = async () => {
  if (!projectId.value || !selectedCaseIds.value.length) return
  const msgId = `batch-${Date.now()}`
  Message.loading({ id: msgId, content: `正在批量执行 ${selectedCaseIds.value.length} 条用例...`, duration: 0 })
  try {
    const res = await apiCaseApi.batchExecute({ project: projectId.value, case_ids: selectedCaseIds.value, environment: selectedEnvId.value })
    const data = unwrapData<any>(res) || {}
    Message.success({ id: msgId, content: `批量执行完成：通过 ${data?.passed_cases ?? '-'} / 失败 ${data?.failed_cases ?? '-'}`, duration: 3500 })
  } catch (err: any) {
    Message.error({ id: msgId, content: err?.error || '批量执行失败', duration: 4000 })
  } finally {
    fetchRecords()
    reportsReloadKey.value += 1
  }
}
const batchAiEnhancing = ref(false)
const batchAiEnhanceCases = async () => {
  if (!selectedCaseIds.value.length) return
  const msgId = `batch-ai-${Date.now()}`
  batchAiEnhancing.value = true
  Message.loading({ id: msgId, content: `正在批量 AI 增强 ${selectedCaseIds.value.length} 条用例...`, duration: 0 })
  try {
    const res = await apiCaseApi.batchAiEnhance({ case_ids: selectedCaseIds.value, apply: true, mode: 'accurate' })
    const data = unwrapData<any>(res) || {}
    Message.success({ id: msgId, content: `批量 AI 增强完成：已增强 ${data?.enhanced_count ?? '-'} / 异常 ${data?.error_count ?? '-'}`, duration: 3500 })
    selectedCaseIds.value = []
  } catch (err: any) {
    Message.error({ id: msgId, content: err?.error || '批量 AI 增强失败', duration: 4000 })
  } finally {
    batchAiEnhancing.value = false
    fetchCases()
  }
}
const enhanceCase = (record: ApiTestCase) => {
  aiDrawerCaseId.value = record.id
  aiDrawerCaseName.value = record.name
  aiDrawerVisible.value = true
  // 打开 drawer 后调一次 load
  setTimeout(() => aiEnhanceDrawerRef.value?.load?.(), 50)
}

const handleDeleteDefinition = async (record: ApiDefinition) => {
  try {
    await apiDefinitionApi.delete(record.id)
    Message.success('已删除')
    fetchDefinitions()
  } catch (err: any) {
    Message.error(err?.error || '删除失败')
  }
}
const handleDeleteCase = async (record: ApiTestCase) => {
  try {
    await apiCaseApi.delete(record.id)
    Message.success('已删除')
    fetchCases()
  } catch (err: any) {
    Message.error(err?.error || '删除失败')
  }
}
const handleDeleteEnv = async (record: ApiEnvironmentConfig) => {
  try {
    await apiEnvApi.delete(record.id)
    Message.success('已删除')
    fetchEnvConfigs()
  } catch (err: any) {
    Message.error(err?.error || '删除失败')
  }
}
const handleDeletePublicData = async (record: ApiPublicData) => {
  try {
    await apiPublicDataApi.delete(record.id)
    Message.success('已删除')
    fetchPublicData()
  } catch (err: any) {
    Message.error(err?.error || '删除失败')
  }
}
const handleDeleteScript = async (record: ApiScript) => {
  try {
    await apiScriptApi.delete(record.id)
    Message.success('已删除')
    fetchScripts()
  } catch (err: any) {
    Message.error(err?.error || '删除失败')
  }
}
const handleGenerateCaseFromDefinition = async (record: ApiDefinition) => {
  try {
    const res = await apiDefinitionApi.generateCase(record.id)
    const data = unwrapData<any>(res)
    Message.success(`已生成用例 #${data.case_id}：${data.name}`)
    fetchCases()
  } catch (err: any) {
    Message.error(err?.error || '生成失败')
  }
}
const handleGenerateFromTrace = () => {
  if (!projectId.value) {
    Message.warning('请先选择项目')
    return
  }
  traceImportVisible.value = true
}
const onTraceImported = () => {
  fetchCases()
  fetchEnvConfigs()
}
const handleGenerateFromFunctional = () => {
  if (!projectId.value) {
    Message.warning('请先选择项目')
    return
  }
  functionalAiVisible.value = true
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
.module-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.module-node-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.module-node-more {
  opacity: 0;
  flex-shrink: 0;
  font-weight: bold;
  letter-spacing: 1px;
}
.module-node:hover .module-node-more {
  opacity: 1;
}
.layout-content {
  flex: 1;
  min-width: 0;
  padding: 20px;
  background: var(--color-bg-2);
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
