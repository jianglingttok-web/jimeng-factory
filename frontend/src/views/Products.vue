<template>
  <div class="page">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h1 style="margin:0">产品列表</h1>
      <button class="btn-primary" @click="showForm = true" v-if="!showForm">+ 新建产品</button>
    </div>

    <!-- 创建产品表单 -->
    <div class="card" v-if="showForm" style="max-width:600px;margin-bottom:20px">
      <h2 style="font-size:15px;margin-bottom:14px">新建产品</h2>
      <div class="alert alert-error" v-if="formError">{{ formError }}</div>

      <label>产品名称</label>
      <input
        v-model="newProduct.name"
        type="text"
        placeholder="例：夏季连衣裙"
        style="width:100%;padding:7px 10px;border:1px solid #d9d9d9;border-radius:4px;font-size:14px"
      />

      <label style="margin-top:14px;display:block">商品图片（1-3 张）</label>
      <input type="file" accept="image/*" multiple ref="fileInput" @change="onFilesSelected" />
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px" v-if="previewUrls.length">
        <img
          v-for="(url, i) in previewUrls" :key="i"
          :src="url"
          style="height:64px;border-radius:4px;object-fit:cover;border:1px solid #eee"
        />
      </div>

      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;margin-bottom:8px">
        <label style="margin:0">Prompt 脚本（每条为一个变体）</label>
        <button type="button" class="btn-primary btn-sm" @click="addPrompt">+ 添加</button>
      </div>
      <div
        v-for="(v, i) in newProduct.variants"
        :key="i"
        style="display:flex;gap:8px;align-items:flex-start;margin-bottom:8px"
      >
        <textarea
          v-model="v.prompt"
          :placeholder="`脚本 ${i + 1}`"
          rows="3"
          style="flex:1;padding:6px 10px;border:1px solid #d9d9d9;border-radius:4px;font-size:13px;resize:vertical"
        />
        <button class="btn-danger btn-sm" @click="removePrompt(i)" style="margin-top:4px">删</button>
      </div>

      <div style="display:flex;gap:8px;margin-top:14px">
        <button class="btn-primary" @click="createProduct" :disabled="creating">
          {{ creating ? '创建中...' : '创建' }}
        </button>
        <button @click="cancelForm" style="background:#f0f0f0">取消</button>
      </div>
    </div>

    <!-- 产品列表 -->
    <div v-if="products.length === 0 && !showForm" style="color:#aaa">暂无产品</div>

    <div class="card" v-for="p in products" :key="p.name">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <strong>{{ p.name }}</strong>
        <div style="display:flex;gap:8px">
          <span style="color:#888;font-size:12px;line-height:28px">{{ p.prompt_variants?.length || 0 }} 个脚本</span>
          <button class="btn-primary btn-sm" @click="startEditing(p)">编辑</button>
          <button class="btn-danger btn-sm" @click="doDelete(p.name)">删除</button>
        </div>
      </div>

      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px" v-if="p.images?.length">
        <span
          v-for="img in p.images" :key="img"
          style="background:#f0f0f0;padding:2px 8px;border-radius:3px;font-size:12px"
        >{{ img }}</span>
      </div>
      <div v-else style="color:#bbb;font-size:12px;margin-bottom:8px">暂无图片</div>

      <div
        v-if="editingProduct === p.name"
        style="border-top:1px solid #f0f0f0;padding-top:12px;display:flex;flex-direction:column;gap:8px"
      >
        <div class="alert alert-error" v-if="editError">{{ editError }}</div>

        <div style="display:flex;justify-content:space-between;align-items:center">
          <label style="margin:0">编辑 Prompt 变体</label>
          <button type="button" class="btn-primary btn-sm" @click="addEditPrompt">+ 添加 prompt</button>
        </div>

        <div
          v-for="(variant, i) in editingVariants"
          :key="`${p.name}-${i}`"
          style="display:flex;gap:8px;align-items:flex-start"
        >
          <textarea
            v-model="variant.prompt"
            :placeholder="`脚本 ${i + 1}`"
            rows="3"
            style="flex:1;padding:6px 10px;border:1px solid #d9d9d9;border-radius:4px;font-size:13px;resize:vertical"
          />
          <button class="btn-danger btn-sm" @click="removeEditPrompt(i)" style="margin-top:4px">删</button>
        </div>

        <div style="display:flex;gap:8px">
          <button class="btn-primary" @click="saveProductEdits(p.name)" :disabled="savingEdit">
            {{ savingEdit ? '保存中...' : '保存' }}
          </button>
          <button @click="cancelEditing" style="background:#f0f0f0">取消</button>
        </div>
      </div>

      <div
        v-else-if="p.prompt_variants?.length"
        style="display:flex;flex-direction:column;gap:4px"
      >
        <div
          v-for="v in p.prompt_variants" :key="v.id"
          style="background:#fafafa;padding:6px 10px;border-radius:4px;font-size:13px;color:#555"
        >{{ v.prompt }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { fetchProducts, updateProduct } from '../api.js'

const products = ref([])
const showForm = ref(false)
const creating = ref(false)
const formError = ref('')
const fileInput = ref(null)
const selectedFiles = ref([])
const previewUrls = ref([])
const editingProduct = ref('')
const editingVariants = ref([])
const editError = ref('')
const savingEdit = ref(false)

const newProduct = ref({ name: '', variants: [{ prompt: '' }] })

async function load() {
  products.value = await fetchProducts()
}

function startEditing(product) {
  editingProduct.value = product.name
  editError.value = ''
  editingVariants.value = (product.prompt_variants || []).map(variant => ({
    id: variant.id,
    title: variant.title || '',
    prompt: variant.prompt || '',
  }))
  if (!editingVariants.value.length) {
    editingVariants.value = [{ prompt: '', title: '' }]
  }
}

function addPrompt() {
  newProduct.value.variants.push({ prompt: '' })
}

function removePrompt(i) {
  if (newProduct.value.variants.length > 1) newProduct.value.variants.splice(i, 1)
}

function addEditPrompt() {
  editingVariants.value.push({ prompt: '', title: '' })
}

function removeEditPrompt(i) {
  if (editingVariants.value.length > 1) editingVariants.value.splice(i, 1)
}

function onFilesSelected(e) {
  selectedFiles.value = Array.from(e.target.files)
  previewUrls.value = selectedFiles.value.map(f => URL.createObjectURL(f))
}

function cancelForm() {
  showForm.value = false
  formError.value = ''
  newProduct.value = { name: '', variants: [{ prompt: '' }] }
  selectedFiles.value = []
  previewUrls.value = []
  if (fileInput.value) fileInput.value.value = ''
}

function cancelEditing() {
  editingProduct.value = ''
  editingVariants.value = []
  editError.value = ''
}

async function createProduct() {
  formError.value = ''
  if (!newProduct.value.name.trim()) { formError.value = '请填写产品名称'; return }
  const validVariants = newProduct.value.variants.filter(v => v.prompt.trim())
  if (!validVariants.length) { formError.value = '至少需要一个 Prompt'; return }

  creating.value = true
  try {
    // 1. 创建产品
    const r = await fetch('/api/products', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newProduct.value.name, variants: validVariants }),
    })
    if (!r.ok) {
      const e = await r.json()
      throw new Error(e.detail || r.statusText)
    }

    // 2. 上传图片（如果有）
    if (selectedFiles.value.length) {
      const fd = new FormData()
      for (const f of selectedFiles.value) fd.append('files', f)
      await fetch(`/api/products/${encodeURIComponent(newProduct.value.name)}/images`, {
        method: 'POST', body: fd,
      })
    }

    cancelForm()
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    creating.value = false
  }
}

async function doDelete(name) {
  if (!confirm(`确认删除产品「${name}」？`)) return
  await fetch(`/api/products/${encodeURIComponent(name)}`, { method: 'DELETE' })
  if (editingProduct.value === name) {
    cancelEditing()
  }
  await load()
}

async function saveProductEdits(name) {
  editError.value = ''
  const variants = editingVariants.value
    .map(variant => ({
      ...(variant.id ? { id: variant.id } : {}),
      title: variant.title || variant.prompt.trim().slice(0, 20),
      prompt: variant.prompt.trim(),
    }))
    .filter(variant => variant.prompt)

  if (!variants.length) {
    editError.value = '至少需要一个 Prompt'
    return
  }

  savingEdit.value = true
  try {
    await updateProduct(name, variants)
    await load()
    cancelEditing()
  } catch (e) {
    editError.value = e.message
  } finally {
    savingEdit.value = false
  }
}

onMounted(load)
</script>
