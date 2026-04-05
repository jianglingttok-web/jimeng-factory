<template>
  <nav v-if="!isLoginPage">
    <span class="brand">即梦内容工厂</span>
    <RouterLink to="/tasks">任务列表</RouterLink>
    <RouterLink to="/submit">下单</RouterLink>
    <RouterLink to="/products">产品</RouterLink>
    <div class="nav-right">
      <span v-if="username" class="username">{{ username }}</span>
      <button class="logout-btn" @click="handleLogout">退出</button>
    </div>
  </nav>
  <RouterView />
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearToken, getToken } from './api.js'

const route = useRoute()
const router = useRouter()

const isLoginPage = computed(() => route.path === '/login')

function parseUsername() {
  const token = getToken()
  if (!token) return ''
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.sub || payload.username || payload.name || ''
  } catch {
    return ''
  }
}

const username = ref(parseUsername())

watch(
  () => route.path,
  () => { username.value = parseUsername() }
)

function handleLogout() {
  clearToken()
  username.value = ''
  router.push('/login')
}
</script>

<style scoped>
nav {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 20px;
  height: 48px;
  background: #fff;
  border-bottom: 1px solid #eee;
}
.brand {
  font-weight: 600;
  margin-right: 8px;
  color: #333;
}
nav a {
  text-decoration: none;
  color: #555;
  font-size: 0.95rem;
}
nav a.router-link-active {
  color: #646cff;
  font-weight: 500;
}
.nav-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}
.username {
  font-size: 0.9rem;
  color: #555;
}
.logout-btn {
  padding: 4px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #fff;
  color: #555;
  font-size: 0.88rem;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}
.logout-btn:hover {
  border-color: #646cff;
  color: #646cff;
}
</style>
