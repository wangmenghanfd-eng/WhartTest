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
            <a-button @click="openDefinitionModal()">手动新增接口</a-button>
          </div>
          <a-table :columns="definitionColumns" :data="definitions" :loading="loading" :pagination="false" :scroll="{ x: 1350 }">
            <template #method="{ record }"><a-tag color="arcoblue">{{ record.method }}</a-tag></template>
            <template #def_summary="{ record }">
              <a-tooltip :content="record.summary || '-'">
                <span class="table-ellipsis-cell">{{ record.summary || '-' }}</span>
              </a-tooltip>
            </template>
            <template #def_tags="{ record }">
              <a-tooltip :content="formatDefinitionTags(record.tags)">
                <span class="table-ellipsis-cell">{{ formatDefinitionTags(record.tags) }}</span>
              </a-tooltip>
            </template>
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
            <a-select v-model="caseFilterEnvId" placeholder="环境筛选" allow-clear style="width: 200px" @change="handleCaseFilterEnvChange">
              <a-option v-for="env in envConfigs" :key="env.id" :value="env.id">{{ env.name }}</a-option>
            </a-select>
            <a-select v-model="selectedExecEnvId" placeholder="执行环境（覆盖）" allow-clear style="width: 220px" @change="handleSelectedExecEnvChange">
              <a-option v-for="env in envConfigs" :key="env.id" :value="env.id">{{ env.name }}</a-option>
            </a-select>
            <a-tag v-if="selectedExecEnvId" color="arcoblue" class="exec-env-tag">当前执行环境：{{ selectedExecEnvName }}</a-tag>
            <a-button @click="handleGenerateFromTrace">UI Trace 转接口用例</a-button>
            <a-button @click="handleGenerateFromFunctional">功能用例转接口用例</a-button>
            <a-button type="primary" @click="openCaseModal()">新增用例</a-button>
            <a-button type="outline" :disabled="!selectedModuleId || !cases.length" @click="openModuleBatchAiModePicker">当前层级一键AI增强</a-button>
            <a-button type="outline" :disabled="!selectedCaseIds.length" @click="openBatchAiModePicker">批量AI增强</a-button>
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
          <div class="batch-ai-summary">
            <icon-info-circle class="batch-ai-summary-icon" />
            <span class="batch-ai-summary-text">前置脚本会在请求发出前执行，后置脚本会在响应返回后执行。项目级脚本会自动继承到所有用例，模块脚本会额外叠加到当前模块下的用例和接口场景。</span>
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

        <a-tab-pane key="scenarios" title="接口场景">
          <ApiAutomationScenarios
            :project-id="projectId"
            :selected-module-id="selectedModuleId"
            :module-options="flatModuleOptions"
            :env-configs="envConfigs"
          />
        </a-tab-pane>

        <a-tab-pane key="public-data" title="公共数据">
          <div class="toolbar">
            <a-input-search v-model="publicDataSearch" placeholder="搜索变量名/变量值" allow-clear @search="fetchPublicData" @clear="fetchPublicData" />
            <a-button type="primary" @click="openPublicDataModal()">新增公共数据</a-button>
          </div>
          <div class="batch-ai-summary">
            <icon-info-circle class="batch-ai-summary-icon" />
            <span class="batch-ai-summary-text">启用后的公共数据会自动进入执行上下文，可在路径、Headers、Query、Body 里直接用 <code>{{ formatVariableRef('variable_name') }}</code> 这种写法引用。当前版本也会在“编辑接口用例”里直接预览哪些变量和脚本会生效。</span>
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
          <div class="batch-ai-summary env-summary-note">
            <icon-info-circle class="batch-ai-summary-icon" />
            <span class="batch-ai-summary-text">这些环境共用同一个 MSS Dev 站点地址，但保存的是不同角色的 Cookie、Token 和环境变量。URL 相同是正常的，分开保存是为了让各角色会话互不覆盖。</span>
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
            <template #batch_status="{ record }"><a-tag :color="getBatchStatusColor(record.status)">{{ BATCH_STATUS_LABELS[record.status] }}</a-tag></template>
            <template #rate="{ record }">{{ record.success_rate?.toFixed?.(1) ?? record.success_rate }}%</template>
            <template #batch_created_at="{ record }">{{ formatDateTime(record.created_at) }}</template>
            <template #batch_duration="{ record }">{{ formatDuration(record.duration) }}</template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="records" title="执行记录">
          <a-table :columns="recordColumns" :data="records" :loading="loading" :pagination="false" :scroll="{ x: 1000 }">
            <template #record_status="{ record }"><a-tag :color="record.status === 2 ? 'green' : record.status === 3 ? 'red' : 'gray'">{{ STATUS_LABELS[record.status] }}</a-tag></template>
            <template #record_created_at="{ record }">{{ formatDateTime(record.created_at) }}</template>
            <template #record_duration="{ record }">{{ formatDuration(record.duration) }}</template>
            <template #error="{ record }">
              <a-tooltip v-if="record.error_message" :content="record.error_message">
                <span class="ellipsis-error">{{ record.error_message }}</span>
              </a-tooltip>
              <span v-else>-</span>
            </template>
          </a-table>
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

    <a-modal v-model:visible="moduleModalVisible" title="接口模块" @before-ok="submitModule">
      <a-input v-model="moduleForm.name" placeholder="模块名称" />
    </a-modal>

    <a-modal v-model:visible="envModalVisible" :title="editingEnvId ? '编辑环境' : '新增环境'" :width="640" @before-ok="submitEnv">
      <a-form layout="vertical">
        <a-form-item label="环境名称" required><a-input v-model="envForm.name" /></a-form-item>
        <a-form-item required>
          <template #label>
            <span class="form-label-with-tip">
              基础 URL
              <a-tooltip content="当接口路径写成 /users 这类相对路径时，会自动拼接这里的基础 URL；如果用例里已经写了完整 URL，则直接按完整地址请求。">
                <icon-info-circle class="inline-help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input v-model="envForm.base_url" placeholder="https://api.example.com" />
        </a-form-item>
        <a-form-item label="默认环境"><a-switch v-model="envForm.is_default" /></a-form-item>
        <a-form-item>
          <template #label>
            <span class="form-label-with-tip">
              Headers（JSON）
              <a-tooltip content="可选。这里填写当前环境下所有请求默认带上的请求头，比如 Authorization、Cookie、X-CSRF-Token、Content-Type。格式示例：{&quot;Authorization&quot;:&quot;Bearer xxx&quot;,&quot;Cookie&quot;:&quot;a=1; b=2&quot;}。用例里单独填写的 headers 会覆盖同名项。">
                <icon-info-circle class="inline-help-icon" />
              </a-tooltip>
            </span>
          </template>
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
            <a-form-item label="默认环境">
              <a-select v-model="caseForm.environment" allow-clear placeholder="不选则执行时使用环境覆盖或项目默认环境">
                <a-option v-for="env in envConfigs" :key="env.id" :value="env.id">{{ env.name }}</a-option>
              </a-select>
            </a-form-item>
            <a-form-item label="路径">
              <a-input v-model="caseForm.path" placeholder="/api/users" />
            </a-form-item>
            <a-form-item>
              <template #label>
                <span class="form-label-with-tip">
                  执行上下文预览
                  <a-tooltip content="这里展示当前用例实际可直接使用的公共变量，以及会自动继承执行的项目级/模块级脚本，方便像 Apifox 一样在编辑时就看清楚上下文。">
                    <icon-info-circle class="inline-help-icon" />
                  </a-tooltip>
                </span>
              </template>
              <div class="case-context-preview">
                <div class="case-context-row">
                  <div class="case-context-label">公共变量</div>
                  <div class="case-context-value">
                    <a-tag v-for="item in enabledPublicDataPreview" :key="item.id" color="arcoblue">{{ formatVariableRef(item.key) }}</a-tag>
                    <span v-if="!enabledPublicDataPreview.length" class="case-context-empty">暂无启用公共数据</span>
                  </div>
                </div>
                <div class="case-context-row">
                  <div class="case-context-label">前置脚本</div>
                  <div class="case-context-value">
                    <a-tag v-for="item in inheritedPreScripts" :key="`pre-${item.id}`" color="green">{{ item.scopeLabel }} · {{ item.name }}</a-tag>
                    <span v-if="!inheritedPreScripts.length" class="case-context-empty">无自动继承前置脚本</span>
                  </div>
                </div>
                <div class="case-context-row">
                  <div class="case-context-label">后置脚本</div>
                  <div class="case-context-value">
                    <a-tag v-for="item in inheritedPostScripts" :key="`post-${item.id}`" color="orange">{{ item.scopeLabel }} · {{ item.name }}</a-tag>
                    <span v-if="!inheritedPostScripts.length" class="case-context-empty">无自动继承后置脚本</span>
                  </div>
                </div>
                <div class="case-context-footnote">真实执行后的变量提取、脚本运行结果仍会落在“执行记录”里；这里展示的是执行前可见的继承关系。</div>
              </div>
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

    <a-modal v-model:visible="scriptModalVisible" :title="editingScriptId ? '编辑脚本' : '新增脚本'" :width="900" @before-ok="submitScript">
      <a-form layout="vertical">
        <a-form-item label="脚本名称" required><a-input v-model="scriptForm.name" /></a-form-item>
        <a-form-item label="所属模块" extra="不选则为项目级脚本。">
          <a-select v-model="scriptForm.module" :options="flatModuleOptions" allow-clear placeholder="项目级脚本" />
        </a-form-item>
        <a-form-item label="类型"><a-select v-model="scriptForm.script_type"><a-option value="pre">前置</a-option><a-option value="post">后置</a-option></a-select></a-form-item>
        <a-form-item label="内容" extra="支持 JavaScript。常用上下文：request、response、variables。">
          <VueMonacoEditor
            v-model:value="scriptForm.content"
            language="javascript"
            :theme="scriptEditorTheme"
            height="360px"
            :options="scriptEditorOptions"
          />
        </a-form-item>
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
        <a-form-item>
          <template #label>
            <span class="form-label-with-tip">
              摘要
              <a-tooltip content="对应 OpenAPI 里的 summary，建议写成一句简短概述。导入 Swagger/OpenAPI 时，这里会优先承接接口文档里的 summary，和 Apifox 的展示方式一致。">
                <icon-info-circle class="inline-help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input v-model="defForm.summary" placeholder="例如：查询危机列表" />
        </a-form-item>
        <a-form-item>
          <template #label>
            <span class="form-label-with-tip">
              标签（逗号分隔）
              <a-tooltip content="对应 OpenAPI 里的 tags。导入时平台会保留 tags；它们主要用于目录分组、搜索和后续批量整理。若标签里带 /，可表达更细的层级语义，和 Apifox 常见的标签分组思路一致。">
                <icon-info-circle class="inline-help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input v-model="defForm.tagsText" placeholder="例如：ncema,crises/list" />
        </a-form-item>
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
      @applied="handleAiEnhanceApplied"
    />

    <a-modal
      v-model:visible="batchAiModePickerVisible"
      title="选择批量 AI 增强模式"
      :width="520"
      ok-text="开始生成预览"
      :ok-button-props="{ loading: batchAiGeneratingPreview, disabled: batchAiGeneratingPreview }"
      :cancel-button-props="{ disabled: batchAiGeneratingPreview }"
      @ok="openBatchAiEnhance"
    >
      <div class="batch-ai-mode-picker">
        <a-radio-group v-model="batchAiMode" direction="vertical" size="large">
          <a-radio value="accurate">
            <div class="batch-ai-mode-option">
              <div class="batch-ai-mode-title">准确模式</div>
              <div class="batch-ai-mode-desc">调用模型逐条生成建议，更慢，但断言和提取规则更稳，适合正式应用前使用。</div>
            </div>
          </a-radio>
          <a-radio value="fast">
            <div class="batch-ai-mode-option">
              <div class="batch-ai-mode-title">快速模式</div>
              <div class="batch-ai-mode-desc">基于最近一次真实响应快速生成启发式建议，速度快，适合先预览大致方向。</div>
            </div>
          </a-radio>
        </a-radio-group>
      </div>
    </a-modal>

    <a-modal
      v-model:visible="batchAiModalVisible"
      title="批量 AI 增强预览"
      :width="920"
      :ok-text="batchAiApplying ? '应用中...' : '应用全部建议'"
      :ok-button-props="{ disabled: !batchAiPreviewItems.length || batchAiLoading, loading: batchAiApplying }"
      :cancel-button-props="{ disabled: batchAiApplying }"
      @cancel="handleBatchAiCancel"
      @before-ok="applyBatchAiEnhance"
    >
      <div v-if="batchAiLoading" class="state-block">
        <a-spin />
        <span style="margin-left: 8px">正在生成批量 AI 增强建议...</span>
      </div>
      <div v-else class="batch-ai-summary">
        <icon-info-circle class="batch-ai-summary-icon" />
        <span class="batch-ai-summary-text">已选 {{ batchAiTargetCaseIds.length || selectedCaseIds.length }} 条用例；有建议 {{ batchAiSummary.enhanced }} 条；异常 {{ batchAiSummary.errors }} 条。当前为{{ batchAiMode === 'accurate' ? '准确模式' : '快速模式' }}。</span>
      </div>
      <div v-if="!batchAiLoading" class="batch-ai-toolbar">
        <div class="batch-ai-toolbar-left">
          <a-tag color="arcoblue">{{ batchAiMode === 'accurate' ? '准确模式' : '快速模式' }}</a-tag>
        </div>
        <a-radio-group v-model="batchAiGroupFilter" type="button" size="small">
          <a-radio value="all">全部</a-radio>
          <a-radio value="POST">POST组</a-radio>
          <a-radio value="GET">GET组</a-radio>
        </a-radio-group>
      </div>
      <a-table
        v-if="!batchAiLoading"
        :data="batchAiVisibleItems"
        :pagination="false"
        :columns="batchAiColumns"
        row-key="case_id"
        size="small"
        :scroll="{ x: 980, y: 420 }"
      >
        <template #batch_ai_case="{ record, rowIndex }">
          <a-button type="text" size="mini" class="batch-ai-case-link" @click="openBatchAiEditor(record, rowIndex)">
            {{ record.case_name }}
          </a-button>
        </template>
        <template #batch_ai_status="{ record }">
          <a-tag v-if="record.error" color="red">失败</a-tag>
          <a-tag v-else-if="record.added_assertions || record.added_extractors" color="green">有建议</a-tag>
          <a-tag v-else color="gray">无新增</a-tag>
        </template>
        <template #batch_ai_rationale="{ record }">
          <a-tooltip :content="record.error || record.rationale || '-'">
            <span class="batch-ai-rationale-cell">{{ record.error || record.rationale || '-' }}</span>
          </a-tooltip>
        </template>
        <template #batch_ai_ops="{ record, rowIndex }">
          <a-button type="text" size="mini" @click="openBatchAiEditor(record, rowIndex)">查看/编辑</a-button>
        </template>
      </a-table>
    </a-modal>

    <a-modal
      v-model:visible="batchAiEditorVisible"
      :title="batchAiEditorTitle"
      :width="860"
      @before-ok="saveBatchAiEditor"
    >
      <div class="batch-ai-summary">
        <icon-info-circle class="batch-ai-summary-icon" />
        <span class="batch-ai-summary-text">{{ batchAiEditorMeta }}</span>
      </div>
      <a-form layout="vertical">
        <a-form-item label="建议说明">
          <a-textarea v-model="batchAiEditRationale" :auto-size="{ minRows: 2, maxRows: 5 }" placeholder="可修改 AI 建议说明；为空时会使用系统默认说明" />
        </a-form-item>
        <a-form-item label="建议断言">
          <AssertionEditor v-model="batchAiEditAssertions" />
        </a-form-item>
        <a-form-item label="建议变量提取">
          <ExtractorEditor v-model="batchAiEditExtractors" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconInfoCircle } from '@arco-design/web-vue/es/icon'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { useProjectStore } from '@/store/projectStore'
import { useThemeStore } from '@/store/themeStore'
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
import ApiAutomationScheduledTasks from '../components/ApiAutomationScheduledTasks.vue'
import ApiAutomationScenarios from '../components/ApiAutomationScenarios.vue'
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
const themeStore = useThemeStore()
const projectId = computed(() => projectStore.currentProject?.id)
const activeTab = ref('definitions')
const loading = ref(false)
const submitting = ref(false)
const selectedModuleId = ref<number | undefined>()
const selectedExecEnvId = ref<number | undefined>()
const caseFilterEnvId = ref<number | undefined>()
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
const batchAiModePickerVisible = ref(false)
const batchAiModalVisible = ref(false)
const batchAiLoading = ref(false)
const batchAiApplying = ref(false)
const batchAiGeneratingPreview = ref(false)
const batchAiPreviewItems = ref<Array<Record<string, any>>>([])
const batchAiMode = ref<'accurate' | 'fast'>('accurate')
const batchAiGroupFilter = ref<'all' | 'POST' | 'GET'>('all')
const batchAiEditorVisible = ref(false)
const batchAiEditingIndex = ref<number>(-1)
const batchAiEditAssertions = ref<Array<Record<string, any>>>([])
const batchAiEditExtractors = ref<Array<Record<string, any>>>([])
const batchAiEditRationale = ref('')
const batchAiOriginalAssertions = ref<Array<Record<string, any>>>([])
const batchAiOriginalExtractors = ref<Array<Record<string, any>>>([])
const batchAiOriginalRationale = ref('')
const batchAiRequestSeq = ref(0)
const BATCH_AI_PREVIEW_TOAST_ID = 'batch-ai-preview'
const batchAiTargetCaseIds = ref<number[]>([])

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
const selectedExecEnvName = computed(() => envConfigs.value.find((env) => env.id === selectedExecEnvId.value)?.name || '')
const currentCaseModuleId = computed(() => caseForm.module ?? selectedModuleId.value)
const enabledPublicDataPreview = computed(() => publicData.value.filter((item) => item.is_enabled))
const inheritedScripts = computed(() => {
  const moduleId = currentCaseModuleId.value
  return scripts.value
    .filter((item) => !item.module || item.module === moduleId)
    .map((item) => ({
      ...item,
      scopeLabel: item.module ? '模块级' : '项目级',
    }))
})
const inheritedPreScripts = computed(() => inheritedScripts.value.filter((item) => item.script_type === 'pre'))
const inheritedPostScripts = computed(() => inheritedScripts.value.filter((item) => item.script_type === 'post'))
const normalizeOptionalNumber = (value: string | number | undefined | null) => {
  if (value === undefined || value === null || value === '') return undefined
  const parsed = Number(value)
  return Number.isNaN(parsed) ? undefined : parsed
}
const handleCaseFilterEnvChange = (value?: string | number) => {
  caseFilterEnvId.value = normalizeOptionalNumber(value)
}
const handleSelectedExecEnvChange = (value?: string | number) => {
  selectedExecEnvId.value = normalizeOptionalNumber(value)
}

const importForm = reactive({ url: '', content: '', create_cases: true })
const moduleForm = reactive({ name: '' })
const envForm = reactive({
  name: '',
  base_url: '',
  is_default: false,
  headersText: '',
  variablesText: '',
})
const caseForm = reactive({ name: '', method: 'GET', path: '', module: undefined as number | undefined, environment: undefined as number | undefined })
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
const scriptEditorOptions = {
  automaticLayout: true,
  minimap: { enabled: false },
  fontSize: 13,
  lineNumbers: 'on',
  scrollBeyondLastLine: false,
  wordWrap: 'on',
  tabSize: 2,
  insertSpaces: true,
}
const scriptEditorTheme = computed(() => (themeStore.isBlack ? 'vs-dark' : 'vs'))

const definitionColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '方法', slotName: 'method', width: 90 },
  { title: '接口名称', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '路径', dataIndex: 'path', ellipsis: true, tooltip: true },
  { title: '摘要', slotName: 'def_summary', width: 220 },
  { title: '标签', slotName: 'def_tags', width: 180 },
  { title: '模块', dataIndex: 'module_name', width: 140 },
  { title: '来源', dataIndex: 'source', width: 100 },
  { title: '操作', slotName: 'def_ops', width: 220, fixed: 'right' as const },
]
const caseColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '方法', slotName: 'method', width: 90 },
  { title: '用例名称', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '路径', dataIndex: 'path', ellipsis: true, tooltip: true },
  { title: '默认环境', dataIndex: 'environment_name', width: 160, ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'status', width: 90 },
  { title: '操作', slotName: 'case_operations', width: 220 },
]
const envColumns = [
  { title: '环境名称', dataIndex: 'name' },
  { title: '角色/会话', render: (data?: { record?: ApiEnvironmentConfig }) => { const r = data?.record; return r ? extractEnvRole(r.name) : '-' } },
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
  { title: '创建时间', slotName: 'record_created_at', width: 180 },
  { title: '耗时', slotName: 'record_duration', width: 100 },
  { title: '错误', slotName: 'error', width: 220 },
]
const batchColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '批次名称', dataIndex: 'name', ellipsis: true, tooltip: true },
  { title: '状态', slotName: 'batch_status', width: 100 },
  { title: '创建时间', slotName: 'batch_created_at', width: 180 },
  { title: '耗时', slotName: 'batch_duration', width: 100 },
  { title: '成功/失败/总计', render: (data?: { record?: ApiBatchExecutionRecord }) => { const r = data?.record; return r ? `${r.passed_cases}/${r.failed_cases}/${r.total_cases}` : '-' } },
  { title: '成功率', slotName: 'rate', width: 90 },
]

const currentParams = () => ({ project: projectId.value, module: selectedModuleId.value, page_size: 500 })
const debounceTimers: Record<string, number | undefined> = {}
const TERMINAL_RECORD_STATUSES = new Set([2, 3])
const TERMINAL_BATCH_STATUSES = new Set([2, 3, 4])

const formatDuration = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${Number(value).toFixed(3)} s`
}

const formatDateTime = (value?: string | null) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const pad = (num: number) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

const formatVariableRef = (key?: string | null) => `\${{${key || ''}}}`

const formatDefinitionTags = (tags?: string[] | null) => {
  if (!Array.isArray(tags) || !tags.length) return '-'
  return tags.filter(Boolean).join(', ')
}

const getBatchStatusColor = (status?: number) => {
  if (status === 2) return 'green'
  if (status === 3 || status === 4) return 'red'
  if (status === 1) return 'arcoblue'
  return 'gray'
}

const extractEnvRole = (name?: string | null) => {
  const raw = String(name || '').trim()
  if (!raw) return '-'
  return raw.replace(/^MSS\s+/i, '').replace(/\s+Dev$/i, '').trim() || raw
}

const runDebounced = (key: string, fn: () => void, delay = 250) => {
  if (debounceTimers[key]) window.clearTimeout(debounceTimers[key])
  debounceTimers[key] = window.setTimeout(fn, delay)
}

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

const waitForRecordCompletion = async (recordId: number, maxAttempts = 30, delay = 1000) => {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const res = await apiRecordApi.getRecord(recordId)
    const record = unwrapData<ApiExecutionRecord>(res)
    if (record && TERMINAL_RECORD_STATUSES.has(record.status)) return record
    await sleep(delay)
  }
  return null
}

const waitForBatchCompletion = async (batchId: number, maxAttempts = 45, delay = 1000) => {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const res = await apiRecordApi.getBatch(batchId)
    const batch = unwrapData<ApiBatchExecutionRecord>(res)
    if (batch && TERMINAL_BATCH_STATUSES.has(batch.status)) return batch
    await sleep(delay)
  }
  return null
}

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
    const res = await apiCaseApi.list({
      ...currentParams(),
      environment: caseFilterEnvId.value || undefined,
      search: caseSearch.value || undefined,
    })
    cases.value = unwrapPage<ApiTestCase>(res).items
  } finally {
    loading.value = false
  }
}
const fetchEnvConfigs = async () => {
  if (!projectId.value) return
  const res = await apiEnvApi.list({ project: projectId.value, search: envSearch.value || undefined, page_size: 200 })
  envConfigs.value = unwrapPage<ApiEnvironmentConfig>(res).items
}
const fetchPublicData = async () => {
  if (!projectId.value) return
  const res = await apiPublicDataApi.list({ project: projectId.value, search: publicDataSearch.value || undefined, page_size: 200 })
  publicData.value = unwrapPage<ApiPublicData>(res).items
}
const fetchScripts = async () => {
  if (!projectId.value) return
  const res = await apiScriptApi.list({ ...currentParams(), page_size: 300 })
  scripts.value = unwrapPage<ApiScript>(res).items
}
const fetchRecords = async () => {
  if (!projectId.value) return
  const [recordRes, batchRes] = await Promise.all([
    apiRecordApi.list({ project: projectId.value, page_size: 200 }),
    apiRecordApi.batches({ project: projectId.value, page_size: 200 }),
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
  await Promise.all([fetchModules(), fetchEnvConfigs()])
  refreshActive()
}

const onModuleSelect = (keys: Array<string | number>) => {
  selectedModuleId.value = keys?.[0] ? Number(keys[0]) : undefined
  refreshActive()
}
const openModuleModal = () => { moduleForm.name = ''; moduleModalVisible.value = true }

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

const openCaseModal = async (record?: ApiTestCase) => {
  if (!publicData.value.length) await fetchPublicData()
  if (!scripts.value.length) await fetchScripts()
  if (record) {
    let latestRecord = record
    try {
      const res = await apiCaseApi.retrieve(record.id)
      latestRecord = unwrapData<ApiTestCase>(res)
    } catch {
      latestRecord = record
    }
    editingCaseId.value = latestRecord.id
    Object.assign(caseForm, {
      name: latestRecord.name,
      method: latestRecord.method,
      path: latestRecord.path,
      module: latestRecord.module,
      environment: latestRecord.environment ?? undefined,
    })
    caseAssertions.value = Array.isArray(latestRecord.assertions) && latestRecord.assertions.length
      ? (latestRecord.assertions as Array<Record<string, any>>).map((it) => ({ ...it }))
      : [{ type: 'status_code', operator: 'lt', expected: 500 }]
    caseExtractors.value = Array.isArray(latestRecord.extractors)
      ? (latestRecord.extractors as Array<Record<string, any>>).map((it) => ({ ...it }))
      : []
  } else {
    editingCaseId.value = null
    Object.assign(caseForm, { name: '', method: 'GET', path: '', module: selectedModuleId.value, environment: undefined })
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
  if (!projectId.value || !moduleForm.name) return done(false)
  await apiModuleApi.create({ project: projectId.value, name: moduleForm.name, parent: selectedModuleId.value ?? null })
  Message.success('模块已创建')
  done(true)
  fetchModules()
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
    environment: caseForm.environment ?? null,
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
    const res = await apiCaseApi.execute(record.id, { environment: selectedExecEnvId.value })
    const data = unwrapData<any>(res) || {}
    fetchRecords()
    reportsReloadKey.value += 1
    const finalRecord = data?.record_id ? await waitForRecordCompletion(data.record_id) : null
    if (!finalRecord) {
      Message.info({ id: msgId, content: '执行已提交，请稍后在执行记录中查看结果', duration: 3500 })
    } else if (finalRecord.status === 3) {
      Message.error({ id: msgId, content: `执行未通过：${finalRecord.error_message || '断言失败'}`, duration: 4000 })
    } else {
      Message.success({ id: msgId, content: `执行完成（耗时 ${formatDuration(finalRecord.duration)}）`, duration: 3000 })
    }
  } catch (err: any) {
    Message.error({ id: msgId, content: err?.error || '执行失败', duration: 4000 })
  } finally {
    fetchRecords()
    fetchCases()
    reportsReloadKey.value += 1
  }
}
const batchExecute = async () => {
  if (!projectId.value || !selectedCaseIds.value.length) return
  const msgId = `batch-${Date.now()}`
  Message.loading({ id: msgId, content: `正在批量执行 ${selectedCaseIds.value.length} 条用例...`, duration: 0 })
  try {
    const res = await apiCaseApi.batchExecute({ project: projectId.value, case_ids: selectedCaseIds.value, environment: selectedExecEnvId.value })
    const data = unwrapData<any>(res) || {}
    Message.loading({ id: msgId, content: `批量执行已提交，正在执行...（批次 #${data?.batch_id ?? '-'}）`, duration: 0 })
    fetchRecords()
    reportsReloadKey.value += 1
    const finalBatch = data?.batch_id ? await waitForBatchCompletion(data.batch_id) : null
    if (!finalBatch) {
      Message.info({ id: msgId, content: '批量执行已提交，请稍后在批量执行或执行记录中查看结果', duration: 4000 })
    } else if (finalBatch.failed_cases > 0) {
      Message.warning({
        id: msgId,
        content: `批量执行完成：通过 ${finalBatch.passed_cases} / 失败 ${finalBatch.failed_cases} / 总计 ${finalBatch.total_cases}`,
        duration: 4500,
      })
    } else {
      Message.success({
        id: msgId,
        content: `批量执行完成：通过 ${finalBatch.passed_cases} / 失败 ${finalBatch.failed_cases} / 总计 ${finalBatch.total_cases}`,
        duration: 3500,
      })
    }
  } catch (err: any) {
    Message.error({ id: msgId, content: err?.error || '批量执行失败', duration: 4000 })
  } finally {
    fetchRecords()
    fetchCases()
    reportsReloadKey.value += 1
  }
}
const enhanceCase = (record: ApiTestCase) => {
  aiDrawerCaseId.value = record.id
  aiDrawerCaseName.value = record.name
  aiDrawerVisible.value = true
  // 打开 drawer 后调一次 load
  setTimeout(() => aiEnhanceDrawerRef.value?.load?.(), 50)
}

const handleAiEnhanceApplied = async (payload: {
  assertions: number
  extractors: number
  toastId: string
  mergedAssertions: Array<Record<string, any>>
  mergedExtractors: Array<Record<string, any>>
}) => {
  try {
    if (aiDrawerCaseId.value) {
      cases.value = cases.value.map((item) => {
        if (item.id !== aiDrawerCaseId.value) return item
        return {
          ...item,
          assertions: payload.mergedAssertions.map((it) => ({ ...it })),
          extractors: payload.mergedExtractors.map((it) => ({ ...it })),
        }
      })
      if (editingCaseId.value === aiDrawerCaseId.value) {
        caseAssertions.value = payload.mergedAssertions.map((it) => ({ ...it }))
        caseExtractors.value = payload.mergedExtractors.map((it) => ({ ...it }))
      }
    }
    Message.success({
      id: payload.toastId,
      content: `AI增强已保存：新增 ${payload.assertions} 条断言，新增 ${payload.extractors} 条提取器。正在刷新列表...`,
      duration: 0,
    })
    await fetchCases()
    Message.success({
      id: payload.toastId,
      content: `AI增强已应用：新增 ${payload.assertions} 条断言，新增 ${payload.extractors} 条提取器`,
      duration: 3000,
    })
  } catch (err: any) {
    Message.error({
      id: payload.toastId,
      content: err?.error || 'AI增强已保存，但刷新列表失败',
      duration: 4000,
    })
  }
}

const batchAiSummary = computed(() => ({
  enhanced: batchAiPreviewItems.value.filter((item) => (item.added_assertions || 0) + (item.added_extractors || 0) > 0 && !item.error).length,
  errors: batchAiPreviewItems.value.filter((item) => item.error).length,
}))

const batchAiVisibleItems = computed(() => {
  if (batchAiGroupFilter.value === 'all') return batchAiPreviewItems.value
  return batchAiPreviewItems.value.filter((item) => String(item.method || '').toUpperCase() === batchAiGroupFilter.value)
})

const batchAiEditingItem = computed(() => {
  if (batchAiEditingIndex.value < 0) return null
  return batchAiPreviewItems.value[batchAiEditingIndex.value] || null
})

const batchAiEditorTitle = computed(() => {
  const item = batchAiEditingItem.value
  return item ? `编辑 AI 建议 - ${item.case_name}` : '编辑 AI 建议'
})

const batchAiEditorMeta = computed(() => {
  const item = batchAiEditingItem.value
  if (!item) return '可在应用前修改当前用例的 AI 建议断言和变量提取。'
  const method = item.method || '-'
  const path = item.path || '-'
  const currentAssertions = Array.isArray(item.current?.assertions) ? item.current.assertions.length : 0
  const currentExtractors = Array.isArray(item.current?.extractors) ? item.current.extractors.length : 0
  return `方法：${method} ｜ 路径：${path} ｜ 当前断言 ${currentAssertions} 条 ｜ 当前提取器 ${currentExtractors} 条`
})

const buildBatchAiRationale = (item?: Record<string, any> | null) => {
  if (!item) return '可在应用前修改当前用例的 AI 建议断言和变量提取。'
  if (item.error) return String(item.error)
  const addedAssertions = Number(item.added_assertions || 0)
  const addedExtractors = Number(item.added_extractors || 0)
  if (addedAssertions || addedExtractors) {
    return `已保留 ${addedAssertions} 条稳定断言建议、${addedExtractors} 条关键提取建议，可点击“查看/编辑”进一步调整。`
  }
  return '当前无稳定新增建议；动态字段、空值等值断言和重复提取器已自动过滤。'
}

const batchAiColumns = [
  { title: '用例', slotName: 'batch_ai_case', width: 260 },
  { title: '分组', dataIndex: 'method', width: 90 },
  { title: '状态', slotName: 'batch_ai_status', width: 90 },
  { title: '新增断言', dataIndex: 'added_assertions', width: 90 },
  { title: '新增提取器', dataIndex: 'added_extractors', width: 100 },
  { title: '说明', slotName: 'batch_ai_rationale', width: 320 },
  { title: '操作', slotName: 'batch_ai_ops', width: 100 },
]

const deepClone = <T>(value: T): T => JSON.parse(JSON.stringify(value ?? null))

const buildDedupKey = (item: Record<string, any>, keys: string[]) =>
  keys.map((key) => JSON.stringify(item?.[key] ?? null)).join('::')

const countDiffItems = (current: Array<Record<string, any>>, suggested: Array<Record<string, any>>, keys: string[]) => {
  const currentSet = new Set((current || []).filter(Boolean).map((item) => buildDedupKey(item, keys)))
  return (suggested || []).filter((item) => item && !currentSet.has(buildDedupKey(item, keys))).length
}

const recomputeBatchAiItem = (item: Record<string, any>) => {
  const currentAssertions = Array.isArray(item.current?.assertions) ? item.current.assertions : []
  const currentExtractors = Array.isArray(item.current?.extractors) ? item.current.extractors : []
  const suggestedAssertions = Array.isArray(item.suggested?.assertions) ? item.suggested.assertions : []
  const suggestedExtractors = Array.isArray(item.suggested?.extractors) ? item.suggested.extractors : []
  item.added_assertions = countDiffItems(currentAssertions, suggestedAssertions, ['type', 'operator', 'expected', 'target', 'path'])
  item.added_extractors = countDiffItems(currentExtractors, suggestedExtractors, ['name', 'source', 'expression', 'path'])
  return item
}

const openBatchAiEditor = (record: Record<string, any>, rowIndex?: number) => {
  const index = batchAiPreviewItems.value.findIndex((item) => item.case_id === record.case_id)
  if (index < 0) return
  batchAiEditingIndex.value = index
  batchAiOriginalAssertions.value = deepClone(batchAiPreviewItems.value[index]?.suggested?.assertions || [])
  batchAiOriginalExtractors.value = deepClone(batchAiPreviewItems.value[index]?.suggested?.extractors || [])
  batchAiOriginalRationale.value = buildBatchAiRationale(batchAiPreviewItems.value[index])
  batchAiEditAssertions.value = deepClone(batchAiOriginalAssertions.value)
  batchAiEditExtractors.value = deepClone(batchAiOriginalExtractors.value)
  batchAiEditRationale.value = batchAiOriginalRationale.value
  batchAiEditorVisible.value = true
}

const saveBatchAiEditor = () => {
  const index = batchAiEditingIndex.value
  if (index < 0 || !batchAiPreviewItems.value[index]) return false
  const nextRationale = (batchAiEditRationale.value || '').trim() || buildBatchAiRationale(batchAiPreviewItems.value[index])
  const unchanged = JSON.stringify(batchAiEditAssertions.value || []) === JSON.stringify(batchAiOriginalAssertions.value || [])
    && JSON.stringify(batchAiEditExtractors.value || []) === JSON.stringify(batchAiOriginalExtractors.value || [])
    && nextRationale === batchAiOriginalRationale.value
  if (unchanged) {
    batchAiEditorVisible.value = false
    return true
  }
  const next = [...batchAiPreviewItems.value]
  const item = { ...next[index] }
  item.suggested = {
    ...(item.suggested || {}),
    assertions: deepClone(batchAiEditAssertions.value || []),
    extractors: deepClone(batchAiEditExtractors.value || []),
  }
  item.rationale = nextRationale
  next[index] = recomputeBatchAiItem(item)
  batchAiPreviewItems.value = next
  batchAiEditorVisible.value = false
  Message.success('已更新当前用例的批量 AI 建议')
  return true
}

const handleBatchAiCancel = () => {
  const wasLoading = batchAiLoading.value
  batchAiRequestSeq.value += 1
  batchAiModePickerVisible.value = false
  batchAiModalVisible.value = false
  batchAiEditorVisible.value = false
  batchAiEditingIndex.value = -1
  batchAiLoading.value = false
  batchAiGeneratingPreview.value = false
  Message.warning({
    id: BATCH_AI_PREVIEW_TOAST_ID,
    content: wasLoading ? '已取消批量 AI 增强预览' : '已取消',
    duration: 1500,
  })
}

const openBatchAiModePicker = () => {
  if (!selectedCaseIds.value.length) return
  batchAiTargetCaseIds.value = [...selectedCaseIds.value]
  batchAiModePickerVisible.value = true
}

const openModuleBatchAiModePicker = () => {
  if (!selectedModuleId.value || !cases.value.length) return
  batchAiTargetCaseIds.value = cases.value.map((item) => item.id)
  batchAiModePickerVisible.value = true
}

const openBatchAiEnhance = async () => {
  if (batchAiGeneratingPreview.value) return
  batchAiGeneratingPreview.value = true
  batchAiModePickerVisible.value = false
  const requestSeq = ++batchAiRequestSeq.value
  batchAiModalVisible.value = true
  batchAiLoading.value = true
  batchAiGroupFilter.value = 'all'
  batchAiPreviewItems.value = []
  const modeLabel = batchAiMode.value === 'accurate' ? '准确' : '快速'
  const targetIds = batchAiTargetCaseIds.value.length ? batchAiTargetCaseIds.value : [...selectedCaseIds.value]
  Message.loading({ id: BATCH_AI_PREVIEW_TOAST_ID, content: `正在为 ${targetIds.length} 条用例生成${modeLabel} AI 增强建议...`, duration: 0 })
  try {
    const res = await apiCaseApi.batchAiEnhance({ case_ids: targetIds, apply: false, mode: batchAiMode.value })
    if (requestSeq !== batchAiRequestSeq.value || !batchAiModalVisible.value) return
    const data = unwrapData<any>(res)
    batchAiPreviewItems.value = Array.isArray(data?.items)
      ? data.items.map((item: Record<string, any>) => {
          const next = recomputeBatchAiItem(item)
          next.rationale = buildBatchAiRationale(next)
          return next
        })
      : []
    Message.success({ id: BATCH_AI_PREVIEW_TOAST_ID, content: `批量 AI 增强预览已生成：有建议 ${data?.enhanced_count ?? 0} 条，异常 ${data?.error_count ?? 0} 条`, duration: 3000 })
  } catch (err: any) {
    if (requestSeq !== batchAiRequestSeq.value || !batchAiModalVisible.value) return
    batchAiModalVisible.value = false
    Message.error({ id: BATCH_AI_PREVIEW_TOAST_ID, content: err?.error || '批量 AI 增强预览失败', duration: 4000 })
  } finally {
    if (requestSeq === batchAiRequestSeq.value) {
      batchAiLoading.value = false
    }
    batchAiGeneratingPreview.value = false
  }
}

const applyBatchAiEnhance = async () => {
  batchAiApplying.value = true
  const msgId = `batch-ai-apply-${Date.now()}`
  const applyItems = batchAiVisibleItems.value
  Message.loading({ id: msgId, content: `正在应用 ${applyItems.length} 条 AI 增强建议...`, duration: 0 })
  try {
    const res = await apiCaseApi.batchAiEnhance({
      case_ids: applyItems.map((item) => item.case_id),
      apply: true,
      items: applyItems,
    })
    const data = unwrapData<any>(res)
    await fetchCases()
    reportsReloadKey.value += 1
    Message.success({
      id: msgId,
      content: `批量 AI 增强已应用：有建议 ${data?.enhanced_count ?? 0} 条，异常 ${data?.error_count ?? 0} 条`,
      duration: 3500,
    })
    batchAiModalVisible.value = false
    return true
  } catch (err: any) {
    Message.error({ id: msgId, content: err?.error || '批量 AI 增强应用失败', duration: 4000 })
    return false
  } finally {
    batchAiApplying.value = false
  }
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
    Message.success(data.replaced ? `已更新原生成用例 #${data.case_id}：${data.name}` : `已生成用例 #${data.case_id}：${data.name}`)
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
  selectedExecEnvId.value = undefined
  caseFilterEnvId.value = undefined
  selectedCaseIds.value = []
  batchAiTargetCaseIds.value = []
  if (projectId.value) refreshAllBase()
}, { immediate: true })
watch(activeTab, refreshActive)
watch(definitionSearch, () => {
  if (activeTab.value === 'definitions') runDebounced('definition-search', fetchDefinitions)
})
watch(caseSearch, () => {
  if (activeTab.value === 'cases') runDebounced('case-search', fetchCases)
})
watch(caseFilterEnvId, () => {
  if (activeTab.value === 'cases') runDebounced('case-env-filter', fetchCases, 0)
})
watch(envSearch, () => {
  if (activeTab.value === 'env') runDebounced('env-search', fetchEnvConfigs)
})
watch(publicDataSearch, () => {
  if (activeTab.value === 'public-data') runDebounced('public-data-search', fetchPublicData)
})
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
  background: var(--theme-surface);
  border-radius: 8px;
  overflow: auto;
  color: var(--theme-text);
}
.layout-content :deep(.arco-table),
.layout-content :deep(.arco-table-container) {
  width: 100%;
}
.layout-content :deep(.arco-table-thead),
.layout-content :deep(.arco-table-thead tr),
.layout-content :deep(.arco-table-th) {
  background: var(--color-fill-2);
}

.layout-content :deep(.arco-table-fixed-right .arco-table-th),
.layout-content :deep(.arco-table-fixed-right .arco-table-td),
.layout-content :deep(.arco-table-fixed-left .arco-table-th),
.layout-content :deep(.arco-table-fixed-left .arco-table-td) {
  background: var(--theme-surface);
}

.layout-content :deep(.arco-table-fixed-right .arco-table-th),
.layout-content :deep(.arco-table-fixed-left .arco-table-th) {
  background: var(--color-fill-2);
}

.layout-content :deep(.arco-table-fixed-right::before),
.layout-content :deep(.arco-table-fixed-left::before) {
  background: transparent;
}

.layout-content :deep(.arco-table .arco-btn-text.arco-btn-size-mini) {
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
}

:root[data-theme='black'] .layout-content :deep(.arco-table .arco-btn-text.arco-btn-size-mini) {
  background-color: rgba(var(--theme-accent-rgb), 0.18) !important;
  border: 1px solid rgba(var(--theme-accent-rgb), 0.28) !important;
  color: #dbeafe !important;
}

:root[data-theme='black'] :deep(.arco-modal-content),
:root[data-theme='black'] :deep(.arco-modal-header),
:root[data-theme='black'] :deep(.arco-modal-body),
:root[data-theme='black'] :deep(.arco-modal-footer) {
  background: var(--theme-surface);
  color: var(--theme-text);
  border-color: var(--theme-border);
}

:root[data-theme='black'] :deep(.monaco-editor),
:root[data-theme='black'] :deep(.monaco-editor-background),
:root[data-theme='black'] :deep(.margin),
:root[data-theme='black'] :deep(.inputarea.ime-input) {
  background: #0f172a !important;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
:root[data-theme='black'] .api-automation-layout {
  color: var(--theme-text);
}
:root[data-theme='black'] .api-automation-layout .module-panel,
:root[data-theme='black'] .api-automation-layout .layout-content {
  box-shadow: var(--theme-shadow);
  border: 1px solid var(--theme-border);
}
:root[data-theme='black'] .api-automation-layout .panel-title {
  color: var(--theme-text);
}
.toolbar :deep(.arco-input-wrapper) {
  max-width: 260px;
}
.batch-ai-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 12px;
}
.batch-ai-mode-picker {
  padding-top: 8px;
}
.batch-ai-mode-option {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-left: 6px;
}
.batch-ai-mode-title {
  font-weight: 600;
  color: var(--color-text-1);
}
.batch-ai-mode-desc {
  color: var(--color-text-3);
  line-height: 1.6;
  font-size: 13px;
}
.batch-ai-toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.batch-ai-mode-tip {
  color: rgb(var(--arcoblue-5));
  font-size: 16px;
  cursor: help;
}
.batch-ai-summary {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(var(--arcoblue-6), 0.12);
  border: 1px solid rgba(var(--arcoblue-6), 0.24);
}
.batch-ai-summary-icon {
  margin-top: 2px;
  color: rgb(var(--arcoblue-5));
  flex: 0 0 auto;
}
.batch-ai-summary-text {
  color: var(--color-text-1);
  line-height: 1.6;
  white-space: normal;
  word-break: break-word;
  flex: 1;
}
.table-ellipsis-cell {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
.batch-ai-case-link {
  padding-left: 0;
}
.batch-ai-rationale-cell {
  display: inline-block;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgb(var(--red-6));
  vertical-align: bottom;
  padding-right: 8px;
}
.exec-env-tag {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.form-label-with-tip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.case-context-preview {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: 8px;
  background: var(--color-fill-2);
  border: 1px solid var(--color-border-2);
}
.case-context-row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 12px;
  align-items: flex-start;
}
.case-context-label {
  font-weight: 600;
  color: var(--color-text-2);
  line-height: 28px;
}
.case-context-value {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 28px;
  align-items: center;
}
.case-context-empty,
.case-context-footnote {
  color: var(--color-text-3);
  font-size: 12px;
  line-height: 1.6;
}
.case-context-footnote {
  padding-top: 4px;
  border-top: 1px dashed var(--color-border-2);
}
.inline-help-icon {
  color: rgb(var(--arcoblue-5));
  cursor: help;
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
:root[data-theme='black'] .batch-ai-summary-text {
  color: #dbeafe;
}
:root[data-theme='black'] .batch-ai-rationale-cell {
  color: #fca5a5;
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
  .case-context-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }
}
</style>
