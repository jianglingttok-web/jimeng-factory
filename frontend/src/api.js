async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  const res = await fetch(path, { ...options, headers })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  return res.json()
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
    headers: {}, // intentionally empty: let fetch set multipart/form-data boundary
    body: formData,
  })
}
