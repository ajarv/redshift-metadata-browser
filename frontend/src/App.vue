<template>
  <div class="app-shell">
    <nav class="top-nav">
      <div class="nav-brand">
        <span class="material-icons">storage</span>
        <span>DB Browser</span>
      </div>
      <div class="nav-links">
        <router-link to="/browse" active-class="active">Browse</router-link>
        <router-link to="/tasks" active-class="active">Tasks</router-link>
      </div>
    </nav>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import './style.css'
</script>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.top-nav {
  display: flex;
  align-items: center;
  padding: 0 24px;
  height: 56px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  gap: 32px;
}
.nav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--primary);
}
.nav-links {
  display: flex;
  gap: 16px;
}
.nav-links a {
  padding: 8px 12px;
  border-radius: 6px;
  color: var(--text-secondary);
  font-weight: 500;
  text-decoration: none;
}
.nav-links a.active {
  background: #e8f0fe;
  color: var(--primary);
}
.main-content {
  flex: 1;
  overflow: hidden;
}
</style>
