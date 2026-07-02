<template>
  <div class="login-page">
    <div class="login-card">
      <h2>Sign In</h2>
      <p>Sign in to access the DB Browser</p>
      <form @submit.prevent="login">
        <div class="form-group">
          <label for="username">Username</label>
          <input id="username" type="text" v-model="username" required>
        </div>
        <div class="form-group">
          <label for="password">Password</label>
          <input id="password" type="password" v-model="password" required>
        </div>
        <p v-if="error" class="error">{{ error }}</p>
        <button type="submit" class="btn btn-primary full-width">Sign In</button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')

async function login() {
  error.value = ''
  try {
    await fetch('/api-auth/login/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value, password: password.value }),
    })
    router.push('/browse')
  } catch {
    error.value = 'Invalid username or password.'
  }
}
</script>

<style scoped>
.login-page { display: flex; align-items: center; justify-content: center; height: 100%; background: var(--background); }
.login-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 40px; width: 380px; }
.login-card h2 { font-size: 24px; margin-bottom: 4px; }
.login-card p { color: var(--text-secondary); margin-bottom: 24px; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 4px; }
.form-group input { width: 100%; }
.error { color: var(--error); font-size: 13px; margin-bottom: 12px; }
.full-width { width: 100%; justify-content: center; }
</style>
