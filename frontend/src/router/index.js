import { createRouter, createWebHistory } from 'vue-router'
import Tasks from '../views/Tasks.vue'
import Submit from '../views/Submit.vue'
import Products from '../views/Products.vue'
import Login from '../views/Login.vue'
import { isAuthenticated } from '../api.js'

const routes = [
  { path: '/', redirect: '/tasks' },
  { path: '/tasks', component: Tasks, meta: { title: '任务列表' } },
  { path: '/submit', component: Submit, meta: { title: '下单' } },
  { path: '/products', component: Products, meta: { title: '产品' } },
  { path: '/login', component: Login, meta: { title: '登录', public: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta.public) return true
  if (!isAuthenticated()) return '/login'
  return true
})

export default router
