<template>
  <div class="search-container">
    <div class="search-input-wrapper">
      <span class="material-icons search-icon">search</span>
      <input
        type="text"
        placeholder="Search tables and views..."
        v-model="query"
        @input="onInput"
        class="search-input">
      <button v-if="query" class="clear-btn" @click="clearSearch">
        <span class="material-icons">close</span>
      </button>
    </div>
    <div v-if="results.length > 0" class="search-results">
      <div
        v-for="r in results" :key="r.fqn"
        class="result-item"
        @click="select(r)">
        <span class="material-icons result-icon">
          {{ r.entity_type === 'TABLE' ? 'table_chart' : 'view_list' }}
        </span>
        <div class="result-info">
          <span class="result-name">{{ r.name }}</span>
          <span class="result-fqn">{{ r.fqn }}</span>
        </div>
        <span class="result-type">{{ r.entity_type }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { searchEntities } from '../services/api.js'

const emit = defineEmits(['select'])

const query = ref('')
const results = ref([])
let debounceTimer = null

function onInput() {
  clearTimeout(debounceTimer)
  if (query.value.length < 2) {
    results.value = []
    return
  }
  debounceTimer = setTimeout(async () => {
    results.value = await searchEntities(query.value)
  }, 300)
}

function select(entity) {
  emit('select', entity)
  results.value = []
  query.value = entity.name
}

function clearSearch() {
  query.value = ''
  results.value = []
}
</script>

<style scoped>
.search-container { position: relative; }
.search-input-wrapper {
  display: flex; align-items: center; background: var(--surface);
  border: 1px solid var(--border); border-radius: 8px; padding: 0 12px;
}
.search-icon { color: var(--text-secondary); font-size: 20px; }
.search-input { flex: 1; border: none; padding: 10px 8px; font-size: 14px; outline: none; }
.clear-btn { background: none; border: none; color: var(--text-secondary); display: flex; padding: 4px; }
.clear-btn .material-icons { font-size: 18px; }
.search-results {
  position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1); max-height: 320px; overflow-y: auto; z-index: 100;
}
.result-item { display: flex; align-items: center; gap: 8px; padding: 10px 12px; cursor: pointer; }
.result-item:hover { background: var(--background); }
.result-icon { color: var(--text-secondary); font-size: 18px; }
.result-info { flex: 1; min-width: 0; }
.result-name { display: block; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.result-fqn { display: block; font-size: 11px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.result-type { font-size: 10px; padding: 2px 6px; border-radius: 4px; background: var(--background); color: var(--text-secondary); font-weight: 500; }
</style>
