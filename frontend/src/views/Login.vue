<template>
  <div class="login-wrap">
    <div class="login-box">
      <h2>即梦内容工厂</h2>
      <form @submit.prevent="handleLogin">
        <div class="field">
          <label for="username">用户名</label>
          <input
            id="username"
            v-model="username"
            type="text"
            autocomplete="username"
            placeholder="请输入用户名"
            required
          />
        </div>
        <div class="field">
          <label for="password">密码</label>
          <input
            id="password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            required
          />
        </div>
        <div v-if="errorMsg" class="error">{{ errorMsg }}</div>
        <button type="submit" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login, setToken } from '../api.js'

const router = useRouter()
const username = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)

async function handleLogin() {
  errorMsg.value = ''
  loading.value = true
  try {
    const data = await login(username.value, password.value)
    setToken(data.access_token)
    router.push('/')
  } catch (e) {
    errorMsg.value = e.message || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: #f5f5f5;
}
.login-box {
  background: #fff;
  border-radius: 8px;
  padding: 40px 36px;
  width: 340px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.1);
}
h2 {
  text-align: center;
  margin: 0 0 28px;
  font-size: 1.3rem;
  color: #333;
}
.field {
  margin-bottom: 16px;
}
label {
  display: block;
  margin-bottom: 6px;
  font-size: 0.9rem;
  color: #555;
}
input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 0.95rem;
  box-sizing: border-box;
  outline: none;
  transition: border-color 0.2s;
}
input:focus {
  border-color: #646cff;
}
.error {
  color: #e53e3e;
  font-size: 0.88rem;
  margin-bottom: 12px;
}
button {
  width: 100%;
  padding: 9px;
  background: #646cff;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 1rem;
  cursor: pointer;
  transition: background 0.2s;
}
button:hover:not(:disabled) {
  background: #535bf2;
}
button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
