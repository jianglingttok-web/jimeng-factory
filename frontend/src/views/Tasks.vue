<template>
  <div class="page">
    <h1>任务列表</h1>

    <div class="status-bar" v-if="status">
      <div class="stat" v-for="(count, key) in status.tasks" :key="key">
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
      <button @click="retryFailed" style="background:#fa8c16;color:#fff">重试失败</button>
      <button
        v-if="selectedIds.length"
        @click="stopSelected"
        style="background:#cf1322;color:#fff"
      >批量停止 ({{ selectedIds.length }})</button>
      <button @click="syncAccounts" style="background:#52c41a;color:#fff">同步账号</button>
    </div>

    <div class="card" style="padding:0;overflow:auto">
      <table>
        <thead>
          <tr>
            <th style="width:36px">
              <input
                v-if="cancellableTasks.length"
                type="checkbox"
                :checked="allCancellableSelected"
                @change="toggleAll($event)"
              />
            </th>
            <th>任务ID</th>
            <th>产品</th>
            <th>账号</th>
            <th>状态</th>
            <th>重试</th>
            <th>创建时间</th>
            <th>错误</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="tasks.length === 0">
            <td colspan="9" style="text-align:center;color:#aaa;padding:24px">暂无任务</td>
          </tr>
          <tr v-for="t in tasks" :key="t.task_id">
            <td>
              <input
                v-if="isCancellable(t.status)"
                v-model="selectedIds"
                type="checkbox"
                :value="t.task_id"
              />
            </td>
            <td style="font-family:monospace;font-size:11px">{{ t.task_id.slice(0,8) }}</td>
            <td>{{ t.product_name }}</td>
            <td>{{ t.account_name }}</td>
            <td><span :class="'badge badge-' + t.status">{{ t.status }}</span></td>
            <td>{{ t.retry_count }}</td>
            <td>{{ formatTime(t.created_at) }}</td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="t.error_message">
              {{ t.error_message || '-' }}
            </td>
            <td>
              <button
                v-if="isCancellable(t.status)"
                class="btn-danger btn-sm"
                @click="stop(t.task_id)"
              >停止</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div style="color:#aaa;font-size:12px">
      共 {{ tasks.length }} 条 · 每 5 秒自动刷新
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
const statuses = ['pending', 'submitting', 'generating', 'downloading', 'succeeded', 'failed']
const cancellableStatuses = ['pending', 'submitting', 'generating', 'downloading']

let timer = null

const cancellableTasks = computed(() => tasks.value.filter(task => isCancellable(task.status)))
const allCancellableSelected = computed(() => (
  cancellableTasks.value.length > 0 &&
  cancellableTasks.value.every(task => selectedIds.value.includes(task.task_id))
))

async function load() {
  const [t, a, s] = await Promise.all([
    fetchTasks({ status: filterStatus.value, account_name: filterAccount.value }),
    fetchAccounts(),
    fetchStatus(),
  ])
  tasks.value = t
  accounts.value = a
  status.value = s

  const availableIds = new Set(cancellableTasks.value.map(task => task.task_id))
  selectedIds.value = selectedIds.value.filter(id => availableIds.has(id))
}

async function stop(id) {
  await stopTask(id)
  selectedIds.value = selectedIds.value.filter(selectedId => selectedId !== id)
  await load()
}

async function stopSelected() {
  if (!selectedIds.value.length) return
  await stopTasksBatch(selectedIds.value)
  selectedIds.value = []
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

function isCancellable(status) {
  return cancellableStatuses.includes(status)
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
  timer = setInterval(load, 5000)
})

onUnmounted(() => clearInterval(timer))
</script>
