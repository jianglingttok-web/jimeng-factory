<template>
  <div class="page">
    <h1>产品列表</h1>

    <div v-if="products.length === 0" style="color:#aaa">暂无产品</div>

    <div class="card" v-for="p in products" :key="p.name">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <strong>{{ p.name }}</strong>
        <span style="color:#888;font-size:12px">{{ p.prompt_variants?.length || 0 }} 个变体</span>
      </div>

      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px" v-if="p.images?.length">
        <span
          v-for="img in p.images"
          :key="img"
          style="background:#f0f0f0;padding:2px 8px;border-radius:3px;font-size:12px"
        >{{ img }}</span>
      </div>

      <table v-if="p.prompt_variants?.length">
        <thead>
          <tr><th>ID</th><th>标题</th><th>Prompt</th></tr>
        </thead>
        <tbody>
          <tr v-for="v in p.prompt_variants" :key="v.id">
            <td style="font-family:monospace;font-size:11px">{{ v.id }}</td>
            <td>{{ v.title }}</td>
            <td style="max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="v.prompt">
              {{ v.prompt }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { fetchProducts } from '../api.js'

const products = ref([])

onMounted(async () => {
  products.value = await fetchProducts()
})
</script>
