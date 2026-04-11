<template>
  <nav>
    <span class="brand">即梦内容工厂</span>
    <RouterLink to="/tasks">任务列表</RouterLink>
    <RouterLink to="/submit">下单</RouterLink>
    <RouterLink to="/products">产品</RouterLink>
  </nav>
  <RouterView />
</template>

<script setup>
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
</style>
