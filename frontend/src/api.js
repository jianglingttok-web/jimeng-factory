async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
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

export function fetchProducts() {
  return request('/api/products')
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
