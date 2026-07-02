import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/browse' },
    { path: '/browse', component: () => import('./components/BrowseView.vue') },
    { path: '/tasks', component: () => import('./components/TaskRunner.vue') },
    { path: '/login', component: () => import('./components/LoginView.vue') },
  ],
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
