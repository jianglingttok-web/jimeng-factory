import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from '../api.js'
import Tasks from '../views/Tasks.vue'
import Submit from '../views/Submit.vue'
import Products from '../views/Products.vue'
import Login from '../views/Login.vue'
const routes = [
  { path: '/login', component: Login, meta: { public: true, title: '登录' } },
  { path: '/', redirect: '/tasks' },
  { path: '/tasks', component: Tasks, meta: { title: '任务列表' } },
  { path: '/submit', component: Submit, meta: { title: '下单' } },
  { path: '/products', component: Products, meta: { title: '产品' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = getToken()
  if (!to.meta.public && !token) return '/login'
  if (to.path === '/login' && token) return '/tasks'
  return true
})

export default router
