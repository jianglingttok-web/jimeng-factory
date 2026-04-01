<template>
  <div class="page">
    <h1>任务列表</h1>

    <!-- 状态总览 -->
    <div class="status-bar" v-if="status">
      <div class="stat" v-for="(count, key) in status.tasks" :key="key">
        <div class="label">{{ key }}</div>
        <div class="value">{{ count }}</div>
      </div>
    </div>

    <!-- 筛选 -->
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
      <button @click="syncAccounts" style="background:#52c41a;color:#fff">同步账号</button>
    </div>

    <!-- 任务表格 -->
    <div class="card" style="padding:0;overflow:auto">
      <table>
        <thead>
          <tr>
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
            <td colspan="8" style="text-align:center;color:#aaa;padding:24px">暂无任务</td>
          </tr>
          <tr v-for="t in tasks" :key="t.task_id">
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
                class="btn-danger btn-sm"
                v-if="['pending','submitting'].includes(t.status)"
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
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchTasks, fetchAccounts, fetchStatus, stopTask, discoverAccounts } from '../api.js'

const tasks = ref([])
const accounts = ref([])
const status = ref(null)
const filterStatus = ref('')
const filterAccount = ref('')
const statuses = ['pending', 'submitting', 'generating', 'downloading', 'succeeded', 'failed']

let timer = null

async function load() {
  const [t, a, s] = await Promise.all([
    fetchTasks({ status: filterStatus.value, account_name: filterAccount.value }),
    fetchAccounts(),
    fetchStatus(),
  ])
  tasks.value = t
  accounts.value = a
  status.value = s
}

async function stop(id) {
  await stopTask(id)
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

onMounted(() => {
  load()
  timer = setInterval(load, 5000)
})

onUnmounted(() => clearInterval(timer))
</script>
