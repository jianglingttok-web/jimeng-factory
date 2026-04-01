import { createRouter, createWebHistory } from 'vue-router'
import Tasks from '../views/Tasks.vue'
import Submit from '../views/Submit.vue'
import Products from '../views/Products.vue'

const routes = [
  { path: '/', redirect: '/tasks' },
  { path: '/tasks', component: Tasks, meta: { title: '任务列表' } },
  { path: '/submit', component: Submit, meta: { title: '下单' } },
  { path: '/products', component: Products, meta: { title: '产品' } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
