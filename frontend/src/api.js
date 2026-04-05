const TOKEN_KEY = 'jimeng_token'

export function getToken() { return localStorage.getItem(TOKEN_KEY) }
export function setToken(token) { localStorage.setItem(TOKEN_KEY, token) }
export function clearToken() { localStorage.removeItem(TOKEN_KEY) }
export function isAuthenticated() { return !!localStorage.getItem(TOKEN_KEY) }

async function request(path, options = {}) {
  const token = getToken()
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(path, {
    ...options,
    headers,
  })
  if (res.status === 401) {
    clearToken()
    window.location.href = '/login'
    return
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  return res.json()
}

export function login(username, password) {
  return fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
  }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`${res.status} ${res.statusText}: ${text}`)
    }
    return res.json()
  })
}

export function getMe() {
  return request('/api/auth/me')
}

export function changePassword(currentPassword, newPassword) {
  return request('/api/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
}

export function fetchStatus() {
  return request('/api/status')
}

export function fetchAccounts() {
  return request('/api/accounts')
}

export function listProducts() {
  return request('/api/products')
}

export function fetchProducts() {
  return listProducts()
}

export function getProduct(name) {
  return request(`/api/products/${encodeURIComponent(name)}`)
}

export function createProduct(data) {
  return request('/api/products', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateProduct(name, variants) {
  return request(`/api/products/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify({ variants }),
  })
}

export function fetchTasks(params = {}) {
  const q = new URLSearchParams()
  if (params.status) q.set('status', params.status)
  if (params.account_name) q.set('account_name', params.account_name)
  if (params.product_name) q.set('product_name', params.product_name)
  const qs = q.toString()
  return request(`/api/tasks${qs ? '?' + qs : ''}`)
}

export function submitTasks(body) {
  return request('/api/tasks/submit', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function stopTask(taskId) {
  return request(`/api/tasks/${taskId}/stop`, { method: 'POST' })
}

export function stopTasksBatch(taskIds) {
  return request('/api/tasks/stop-batch', {
    method: 'POST',
    body: JSON.stringify({ task_ids: taskIds }),
  })
}

export function retryFailedTasks() {
  return request('/api/tasks/retry-failed', { method: 'POST' })
}

export function discoverAccounts() {
  return request('/api/accounts/discover', { method: 'POST' })
}

export function deleteProduct(name) {
  return request(`/api/products/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export function uploadProductImages(name, formData) {
  return request(`/api/products/${encodeURIComponent(name)}/images`, {
    method: 'POST',
    headers: {},
    body: formData,
  })
}
