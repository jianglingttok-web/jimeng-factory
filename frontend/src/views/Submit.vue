<template>
  <div class="page">
    <h1>下单</h1>

    <div class="card" style="max-width:480px">
      <div class="alert alert-success" v-if="result">
        成功创建 {{ result.created }} 个任务
      </div>
      <div class="alert alert-error" v-if="error">{{ error }}</div>

      <form @submit.prevent="submit">
        <label>产品</label>
        <select v-model="form.product_name" required>
          <option value="" disabled>选择产品</option>
          <option v-for="p in products" :key="p.name" :value="p.name">
            {{ p.name }} ({{ p.prompt_variants?.length || 0 }} 个变体)
          </option>
        </select>

        <label>账号</label>
        <select v-model="form.account_name" required>
          <option value="" disabled>选择账号</option>
          <option v-for="a in accounts" :key="a.name" :value="a.name">
            {{ a.name }} · {{ a.generating_count }}/{{ a.max_concurrent }} 并发
          </option>
        </select>

        <label>数量</label>
        <input type="number" v-model.number="form.count" min="1" max="100" required />

        <div style="margin-top:20px">
          <button type="submit" class="btn-primary" :disabled="loading">
            {{ loading ? '提交中...' : '创建任务' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { fetchProducts, fetchAccounts, submitTasks } from '../api.js'

const products = ref([])
const accounts = ref([])
const loading = ref(false)
const result = ref(null)
const error = ref('')

const form = ref({
  product_name: '',
  account_name: '',
  count: 5,
})

async function submit() {
  loading.value = true
  result.value = null
  error.value = ''
  try {
    result.value = await submitTasks(form.value)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const [p, a] = await Promise.all([fetchProducts(), fetchAccounts()])
  products.value = p
  accounts.value = a
})
</script>
