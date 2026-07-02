<template>
  <div class="tasks-page">
    <h2>Task Runner</h2>
    <p class="subtitle">Run background tasks for metadata fetching, term computation, and PHI classification.</p>

    <div class="task-controls">
      <div class="form-group">
        <label>Task</label>
        <select v-model="selectedTask">
          <option v-for="task in availableTasks" :key="task.name" :value="task.name">
            {{ task.description }}
          </option>
        </select>
      </div>
      <div class="form-group">
        <label>Schema (optional)</label>
        <input type="text" v-model="schemaFilter" placeholder="e.g. accounts_raw">
      </div>
      <div class="form-row">
        <label class="checkbox-label">
          <input type="checkbox" v-model="recompute"> Recompute existing
        </label>
        <div class="form-group workers-group">
          <label>Workers</label>
          <input type="number" v-model.number="workers" min="1" max="16">
        </div>
      </div>
      <button class="btn btn-primary" @click="handleRunTask" :disabled="!selectedTask">
        <span class="material-icons">play_arrow</span> Run Task
      </button>
    </div>

    <div class="recent-tasks">
      <h3>Recent Tasks</h3>
      <p v-if="recentTasks.length === 0" class="no-tasks">No tasks have been run yet.</p>
      <div v-for="task in recentTasks" :key="task.id" class="task-card" :class="'task-' + task.state">
        <div class="task-header">
          <span class="task-name">{{ task.task_name }}</span>
          <span :class="'task-state badge-' + task.state">{{ task.state }}</span>
        </div>
        <div v-if="task.state === 'running'" class="task-progress">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: (task.progress_total > 0 ? (task.progress_current / task.progress_total * 100) : 0) + '%' }"></div>
          </div>
          <span v-if="task.progress_total > 0" class="progress-text">{{ task.progress_current }}/{{ task.progress_total }}</span>
        </div>
        <p v-if="task.message" class="task-message">{{ task.message }}</p>
        <div class="task-time">
          Started: {{ formatDate(task.started_at) }}
          <span v-if="task.completed_at"> | Completed: {{ formatDate(task.completed_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { getTasks, runTask } from '../services/api.js'

const availableTasks = ref([])
const recentTasks = ref([])
const selectedTask = ref('')
const schemaFilter = ref('')
const recompute = ref(false)
const workers = ref(4)
let pollInterval = null

onMounted(async () => {
  await loadTasks()
  pollInterval = setInterval(loadTasks, 5000)
})

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})

async function loadTasks() {
  const data = await getTasks()
  availableTasks.value = data.available
  recentTasks.value = data.recent
  if (!selectedTask.value && data.available.length > 0) {
    selectedTask.value = data.available[0].name
  }
}

async function handleRunTask() {
  const request = { task_name: selectedTask.value, workers: workers.value }
  if (schemaFilter.value) request.schema = schemaFilter.value
  if (recompute.value) request.recompute = true
  const status = await runTask(request)
  recentTasks.value.unshift(status)
}

function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString()
}
</script>

<style scoped>
.tasks-page { max-width: 800px; margin: 0 auto; padding: 32px 24px; }
h2 { font-size: 24px; margin-bottom: 4px; }
.subtitle { color: var(--text-secondary); margin-bottom: 24px; }
.task-controls {
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 24px; display: flex; flex-direction: column; gap: 16px; margin-bottom: 32px;
}
.form-group { display: flex; flex-direction: column; gap: 4px; }
.form-group label { font-size: 12px; font-weight: 500; color: var(--text-secondary); text-transform: uppercase; }
.form-row { display: flex; align-items: center; gap: 24px; }
.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 14px; cursor: pointer; }
.workers-group { width: 80px; }
.workers-group input { width: 60px; }
.recent-tasks { margin-top: 16px; }
.recent-tasks h3 { font-size: 16px; margin-bottom: 12px; }
.no-tasks { color: var(--text-secondary); font-style: italic; }
.task-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 8px; }
.task-card.task-running { border-color: var(--primary); }
.task-card.task-failed { border-color: var(--error); }
.task-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.task-name { font-weight: 600; }
.task-state { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
.badge-running { background: #e3f2fd; color: var(--primary); }
.badge-completed { background: #e8f5e9; color: var(--success); }
.badge-failed { background: #fce8e6; color: var(--error); }
.badge-pending { background: var(--background); color: var(--text-secondary); }
.task-progress { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.progress-bar { flex: 1; height: 6px; background: var(--background); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--primary); border-radius: 3px; transition: width 0.5s; }
.progress-text { font-size: 12px; color: var(--text-secondary); }
.task-message { font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; }
.task-time { font-size: 11px; color: var(--text-secondary); }
</style>
