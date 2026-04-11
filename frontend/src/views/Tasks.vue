<template>
  <div class="page">
    <h1>任务列表</h1>

    <div v-if="status" class="status-bar">
      <div v-for="(count, key) in status.tasks" :key="key" class="stat">
        <div class="label">{{ key }}</div>
        <div class="value">{{ count }}</div>
      </div>
    </div>

    <div class="filters">
      <select v-model="filterStatus" @change="load">
        <option value="">全部状态</option>
        <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
      </select>
      <select v-model="filterAccount" @change="load">
        <option value="">全部账号</option>
        <option v-for="a in accounts" :key="a.name" :value="a.name">
          {{ a.name }} ({{ a.generating_count }}/{{ a.max_concurrent }})
        </option>
      </select>
      <button class="btn-primary" @click="load">刷新</button>
      <button style="background:#fa8c16;color:#fff" @click="retryFailed">重试失败</button>
      <button
        v-if="selectedIds.length"
        style="background:#cf1322;color:#fff"
        @click="stopSelected"
      >
        批量停止 ({{ selectedIds.length }})
      </button>
      <button style="background:#52c41a;color:#fff" @click="syncAccounts">同步账号</button>
    </div>

    <div class="card" style="padding:0;overflow:auto">
      <table>
        <thead>
          <tr>
            <th style="width:36px">
              <input
                v-if="cancellableTasks.length"
                :checked="allCancellableSelected"
                type="checkbox"
                @change="toggleAll($event)"
              />
            </th>
            <th>任务 ID</th>
            <th>产品</th>
            <th>账号</th>
            <th>状态</th>
            <th>重试</th>
            <th>创建时间</th>
            <th>错误摘要</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="tasks.length === 0">
            <td colspan="9" style="padding:24px;text-align:center;color:#aaa">暂无任务</td>
          </tr>
          <template v-for="task in tasks" :key="task.task_id">
            <tr>
              <td>
                <input
                  v-if="isCancellable(task.status)"
                  v-model="selectedIds"
                  :value="task.task_id"
                  type="checkbox"
                />
              </td>
              <td style="font-family:monospace;font-size:11px">{{ task.task_id.slice(0, 8) }}</td>
              <td>{{ task.product_name }}</td>
              <td>{{ task.account_name }}</td>
              <td>
                <span :class="'badge badge-' + task.status">{{ task.status }}</span>
              </td>
              <td>{{ task.retry_count }}</td>
              <td>{{ formatTime(task.created_at) }}</td>
              <td
                :title="task.error_message"
                style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
              >
                {{ task.error_message || '-' }}
              </td>
              <td style="white-space:nowrap">
                <button class="btn-sm" @click="toggleExpanded(task.task_id)">
                  {{ expandedTaskId === task.task_id ? '收起' : '详情' }}
                </button>
                <button
                  v-if="isCancellable(task.status)"
                  class="btn-danger btn-sm"
                  @click="stop(task.task_id)"
                >
                  停止
                </button>
              </td>
            </tr>
            <tr v-if="expandedTaskId === task.task_id">
              <td colspan="9" style="padding:0;background:#fafafa">
                <div style="display:grid;gap:12px;padding:16px">
                  <div style="display:flex;flex-wrap:wrap;gap:12px 24px">
                    <div>
                      <strong>状态：</strong>
                      <span :style="{ color: statusColors[task.status] || '#999', fontWeight: 600 }">
                        {{ task.status }}
                      </span>
                    </div>
                    <div><strong>重试次数：</strong>{{ task.retry_count }} / {{ task.max_retries }}</div>
                    <div><strong>提交时间：</strong>{{ formatTime(task.submitted_at) }}</div>
                    <div><strong>更新时间：</strong>{{ formatTime(task.updated_at) }}</div>
                  </div>
                  <div>
                    <strong>错误信息：</strong>
                    <div :style="{ color: task.status === 'failed' ? '#ff4d4f' : '#666', marginTop: '4px' }">
                      {{ task.error_message || '-' }}
                    </div>
                  </div>
                  <div>
                    <strong>视频路径：</strong>
                    <div style="margin-top:4px;word-break:break-all">
                      {{ task.result_video_path || '-' }}
                    </div>
                  </div>
                  <div>
                    <strong>结果 URL：</strong>
                    <div style="margin-top:4px;word-break:break-all">
                      <a
                        v-if="task.result_url"
                        :href="task.result_url"
                        rel="noreferrer"
                        target="_blank"
                      >
                        {{ task.result_url }}
                      </a>
                      <span v-else>-</span>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div style="font-size:12px;color:#aaa">
      共 {{ tasks.length }} 条任务，每 5 秒自动刷新
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  discoverAccounts,
  fetchAccounts,
  fetchStatus,
  fetchTasks,
  retryFailedTasks,
  stopTask,
  stopTasksBatch,
} from '../api.js'

const tasks = ref([])
const accounts = ref([])
const status = ref(null)
const filterStatus = ref('')
const filterAccount = ref('')
const selectedIds = ref([])
const expandedTaskId = ref('')
const statuses = ['pending', 'submitting', 'generating', 'downloading', 'succeeded', 'failed']
const cancellableStatuses = ['pending', 'submitting', 'generating', 'downloading']
const statusColors = {
  pending: '#999',
  submitting: '#1890ff',
  generating: '#faad14',
  downloading: '#1890ff',
  succeeded: '#52c41a',
  failed: '#ff4d4f',
}

let timer = null
let slowTimer = null

const cancellableTasks = computed(() => tasks.value.filter(task => isCancellable(task.status)))
const allCancellableSelected = computed(() => (
  cancellableTasks.value.length > 0 &&
  cancellableTasks.value.every(task => selectedIds.value.includes(task.task_id))
))

async function loadTasks() {
  const res = await fetchTasks({ status: filterStatus.value, account_name: filterAccount.value })
  tasks.value = res.tasks ?? res

  const availableIds = new Set(cancellableTasks.value.map(task => task.task_id))
  selectedIds.value = selectedIds.value.filter(id => availableIds.has(id))

  if (expandedTaskId.value && !tasks.value.some(task => task.task_id === expandedTaskId.value)) {
    expandedTaskId.value = ''
  }
}

async function loadSlow() {
  const [accountList, nextStatus] = await Promise.all([fetchAccounts(), fetchStatus()])
  accounts.value = accountList
  status.value = nextStatus
}

async function load() {
  await Promise.all([loadTasks(), loadSlow()])
}

async function stop(taskId) {
  await stopTask(taskId)
  selectedIds.value = selectedIds.value.filter(id => id !== taskId)
  if (expandedTaskId.value === taskId) {
    expandedTaskId.value = ''
  }
  await load()
}

async function stopSelected() {
  if (!selectedIds.value.length) return
  await stopTasksBatch(selectedIds.value)
  selectedIds.value = []
  expandedTaskId.value = ''
  await load()
}

async function retryFailed() {
  await retryFailedTasks()
  await load()
}

async function syncAccounts() {
  await discoverAccounts()
  await load()
}

function formatTime(ts) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false })
}

function isCancellable(taskStatus) {
  return cancellableStatuses.includes(taskStatus)
}

function toggleExpanded(taskId) {
  expandedTaskId.value = expandedTaskId.value === taskId ? '' : taskId
}

function toggleAll(event) {
  if (event.target.checked) {
    selectedIds.value = cancellableTasks.value.map(task => task.task_id)
    return
  }
  selectedIds.value = []
}

onMounted(() => {
  load()
  timer = setInterval(loadTasks, 5000)
  slowTimer = setInterval(loadSlow, 30000)
})

onUnmounted(() => {
  clearInterval(timer)
  clearInterval(slowTimer)
})
</script>
