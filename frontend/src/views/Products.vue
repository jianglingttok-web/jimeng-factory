<template>
  <div class="page">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h1 style="margin:0">产品列表</h1>
      <button class="btn-primary" @click="showForm = true">+ 新建产品</button>
    </div>

    <!-- 创建产品表单 -->
    <div class="card" v-if="showForm" style="max-width:600px;margin-bottom:20px">
      <h2 style="font-size:15px;margin-bottom:12px">新建产品</h2>
      <div class="alert alert-error" v-if="formError">{{ formError }}</div>

      <label>产品名称</label>
      <input
        v-model="newProduct.name"
        type="text"
        placeholder="例：夏季连衣裙"
        style="width:100%;padding:7px 10px;border:1px solid #d9d9d9;border-radius:4px;font-size:14px;margin-bottom:4px"
      />

      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:14px;margin-bottom:6px">
        <label style="margin:0">脚本变体</label>
        <button type="button" class="btn-primary btn-sm" @click="addVariant">+ 添加变体</button>
      </div>
      <div
        v-for="(v, i) in newProduct.variants"
        :key="i"
        style="border:1px solid #eee;border-radius:4px;padding:10px;margin-bottom:8px"
      >
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
          <input
            v-model="v.title"
            type="text"
            placeholder="变体标题"
            style="flex:1;padding:5px 8px;border:1px solid #d9d9d9;border-radius:4px;font-size:13px"
          />
          <button class="btn-danger btn-sm" @click="removeVariant(i)">删除</button>
        </div>
        <textarea
          v-model="v.prompt"
          placeholder="Prompt 内容"
          rows="3"
          style="width:100%;padding:5px 8px;border:1px solid #d9d9d9;border-radius:4px;font-size:13px;resize:vertical"
        />
      </div>

      <div style="display:flex;gap:8px;margin-top:12px">
        <button class="btn-primary" @click="createProduct" :disabled="creating">
          {{ creating ? '创建中...' : '创建产品' }}
        </button>
        <button @click="cancelForm" style="background:#f0f0f0">取消</button>
      </div>
    </div>

    <!-- 图片上传对话框 -->
    <div class="card" v-if="uploadTarget" style="max-width:480px;margin-bottom:20px">
      <h2 style="font-size:15px;margin-bottom:10px">上传图片 — {{ uploadTarget }}</h2>
      <div class="alert alert-success" v-if="uploadResult">已上传：{{ uploadResult.join(', ') }}</div>
      <div class="alert alert-error" v-if="uploadError">{{ uploadError }}</div>
      <input type="file" accept="image/*" multiple ref="fileInput" @change="onFilesSelected" />
      <div style="display:flex;gap:8px;margin-top:10px">
        <button class="btn-primary" @click="uploadImages" :disabled="!selectedFiles.length || uploading">
          {{ uploading ? '上传中...' : '上传' }}
        </button>
        <button @click="uploadTarget = null; uploadResult = null; uploadError = ''" style="background:#f0f0f0">关闭</button>
      </div>
    </div>

    <!-- 产品列表 -->
    <div v-if="products.length === 0 && !showForm" style="color:#aaa">暂无产品</div>

    <div class="card" v-for="p in products" :key="p.name">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <strong>{{ p.name }}</strong>
        <div style="display:flex;gap:8px">
          <button class="btn-primary btn-sm" @click="uploadTarget = p.name; uploadResult = null">上传图片</button>
          <button class="btn-danger btn-sm" @click="deleteProduct(p.name)">删除</button>
        </div>
      </div>

      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px" v-if="p.images?.length">
        <span
          v-for="img in p.images" :key="img"
          style="background:#f0f0f0;padding:2px 8px;border-radius:3px;font-size:12px"
        >{{ img }}</span>
      </div>
      <div v-else style="color:#bbb;font-size:12px;margin-bottom:10px">暂无图片</div>

      <table v-if="p.prompt_variants?.length">
        <thead><tr><th>ID</th><th>标题</th><th>Prompt</th></tr></thead>
        <tbody>
          <tr v-for="v in p.prompt_variants" :key="v.id">
            <td style="font-family:monospace;font-size:11px">{{ v.id }}</td>
            <td>{{ v.title }}</td>
            <td style="max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="v.prompt">{{ v.prompt }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { fetchProducts, deleteProduct as apiDelete } from '../api.js'

const products = ref([])
const showForm = ref(false)
const creating = ref(false)
const formError = ref('')

const newProduct = ref({ name: '', variants: [{ title: '', prompt: '' }] })

const uploadTarget = ref(null)
const selectedFiles = ref([])
const uploading = ref(false)
const uploadResult = ref(null)
const uploadError = ref('')
const fileInput = ref(null)

async function load() {
  products.value = await fetchProducts()
}

function addVariant() {
  newProduct.value.variants.push({ title: '', prompt: '' })
}

function removeVariant(i) {
  newProduct.value.variants.splice(i, 1)
}

function cancelForm() {
  showForm.value = false
  formError.value = ''
  newProduct.value = { name: '', variants: [{ title: '', prompt: '' }] }
}

async function createProduct() {
  formError.value = ''
  if (!newProduct.value.name.trim()) { formError.value = '请填写产品名称'; return }
  if (!newProduct.value.variants.length) { formError.value = '至少需要一个变体'; return }
  creating.value = true
  try {
    await fetch('/api/products', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newProduct.value),
    }).then(r => { if (!r.ok) return r.json().then(e => { throw new Error(e.detail || r.statusText) }) })
    cancelForm()
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    creating.value = false
  }
}

function onFilesSelected(e) {
  selectedFiles.value = Array.from(e.target.files)
}

async function uploadImages() {
  uploading.value = true
  uploadError.value = ''
  uploadResult.value = null
  try {
    const fd = new FormData()
    for (const f of selectedFiles.value) fd.append('files', f)
    const r = await fetch(`/api/products/${encodeURIComponent(uploadTarget.value)}/images`, {
      method: 'POST', body: fd,
    })
    const data = await r.json()
    if (!r.ok) throw new Error(data.detail || r.statusText)
    uploadResult.value = data.saved
    selectedFiles.value = []
    if (fileInput.value) fileInput.value.value = ''
    await load()
  } catch (e) {
    uploadError.value = e.message
  } finally {
    uploading.value = false
  }
}

async function deleteProduct(name) {
  if (!confirm(`确认删除产品「${name}」及所有文件？`)) return
  await fetch(`/api/products/${encodeURIComponent(name)}`, { method: 'DELETE' })
  await load()
}

onMounted(load)
</script>
