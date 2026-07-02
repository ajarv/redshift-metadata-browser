<template>
  <div class="browse-layout">
    <aside class="sidebar">
      <div class="sidebar-header">
        <h3>Schemas</h3>
      </div>
      <div class="tree-container">
        <div v-if="loading" class="loading">Loading schemas...</div>
        <div v-for="node in treeNodes" :key="node.fqn" class="tree-node">
          <div
            class="tree-item schema-item"
            :class="{ selected: selectedFqn === node.fqn }"
            @click="toggleNode(node)">
            <span class="material-icons expand-icon">
              {{ node.expanded ? 'expand_more' : 'chevron_right' }}
            </span>
            <span class="material-icons node-icon">folder</span>
            <span class="node-name">{{ node.name }}</span>
          </div>
          <div v-if="node.expanded">
            <div v-if="node.loading" class="tree-child loading-child">Loading...</div>
            <div v-for="child in node.children" :key="child.fqn" class="tree-child">
              <div
                class="tree-item child-item"
                :class="{ selected: selectedFqn === child.fqn }"
                @click="selectTableOrView(child)">
                <span class="material-icons node-icon">
                  {{ child.entity_type === 'TABLE' ? 'table_chart' : 'view_list' }}
                </span>
                <span class="node-name">{{ child.name }}</span>
                <span class="type-badge">{{ child.entity_type }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <!-- Columns Panel (middle, collapsible) -->
    <aside v-if="showColumnsPanel" class="columns-panel" :class="{ collapsed: columnsCollapsed }">
      <div class="columns-header">
        <h3 v-if="!columnsCollapsed">Columns ({{ columns.length }})</h3>
        <button class="collapse-btn" @click="columnsCollapsed = !columnsCollapsed" :title="columnsCollapsed ? 'Expand columns' : 'Collapse columns'">
          <span class="material-icons">{{ columnsCollapsed ? 'chevron_right' : 'chevron_left' }}</span>
        </button>
      </div>
      <div v-if="!columnsCollapsed" class="columns-list">
        <div v-if="columnsLoading" class="loading">Loading columns...</div>
        <div
          v-for="col in columns" :key="col.fqn"
          class="column-item"
          :class="{ selected: selectedColumnFqn === col.fqn }"
          @click="selectColumn(col)">
          <span class="material-icons col-icon">view_column</span>
          <div class="col-info">
            <span class="col-name">{{ col.name }}</span>
            <span v-if="col.metadata && col.metadata.data_type" class="col-type">{{ col.metadata.data_type }}</span>
          </div>
          <span v-if="col.phi_score > 0" class="col-badge phi" :title="'PHI: ' + col.phi_score">{{ col.phi_score }}</span>
          <span v-if="col.pii_score > 0" class="col-badge pii" :title="'PII: ' + col.pii_score">{{ col.pii_score }}</span>
        </div>
      </div>
    </aside>

    <section class="center-panel">
      <SearchBox @select="selectFromSearch" />
      <EntityDetail v-if="detailEntity" :entity="detailEntity" />
      <div v-else class="empty-state">
        <span class="material-icons">touch_app</span>
        <p>Select an entity from the tree or search to view details</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getSchemas, getSchemaChildren, getEntity, getEntityChildren } from '../services/api.js'
import SearchBox from './SearchBox.vue'
import EntityDetail from './EntityDetail.vue'

const route = useRoute()
const router = useRouter()

const treeNodes = ref([])
const loading = ref(true)
const selectedFqn = ref(null)
const selectedEntity = ref(null)
const detailEntity = ref(null)

const columns = ref([])
const columnsLoading = ref(false)
const columnsCollapsed = ref(false)
const selectedColumnFqn = ref(null)

const showColumnsPanel = computed(() => {
  return selectedEntity.value &&
    (selectedEntity.value.entity_type === 'TABLE' || selectedEntity.value.entity_type === 'VIEW')
})

onMounted(async () => {
  try {
    const schemas = await getSchemas()
    treeNodes.value = schemas.map(s => ({
      ...s,
      children: [],
      expanded: false,
      loaded: false,
      loading: false,
    }))
  } finally {
    loading.value = false
  }

  if (route.query.fqn) {
    await loadEntityByFqn(route.query.fqn)
  }
})

async function toggleNode(node) {
  if (node.expanded) {
    node.expanded = false
    return
  }
  node.expanded = true
  if (!node.loaded) {
    node.loading = true
    try {
      const children = await getSchemaChildren(node.name)
      node.children = children
      node.loaded = true
    } finally {
      node.loading = false
    }
  }
}

async function selectTableOrView(entity) {
  selectedFqn.value = entity.fqn
  selectedColumnFqn.value = null
  router.replace({ query: { fqn: entity.fqn } })

  selectedEntity.value = entity
  detailEntity.value = await getEntity(entity.fqn)

  columnsLoading.value = true
  try {
    const children = await getEntityChildren(entity.fqn)
    columns.value = children.filter(c => c.entity_type === 'COLUMN')
  } catch {
    columns.value = []
  } finally {
    columnsLoading.value = false
  }
}

async function selectColumn(col) {
  selectedColumnFqn.value = col.fqn
  router.replace({ query: { fqn: col.fqn } })
  try {
    detailEntity.value = await getEntity(col.fqn)
  } catch {
    detailEntity.value = null
  }
}

async function selectFromSearch(entity) {
  selectedFqn.value = entity.fqn
  selectedColumnFqn.value = null
  router.replace({ query: { fqn: entity.fqn } })

  if (entity.entity_type === 'TABLE' || entity.entity_type === 'VIEW') {
    selectedEntity.value = entity
    detailEntity.value = await getEntity(entity.fqn)
    columnsLoading.value = true
    try {
      const children = await getEntityChildren(entity.fqn)
      columns.value = children.filter(c => c.entity_type === 'COLUMN')
    } catch {
      columns.value = []
    } finally {
      columnsLoading.value = false
    }
  } else {
    selectedEntity.value = null
    columns.value = []
    detailEntity.value = await getEntity(entity.fqn)
  }
}

async function loadEntityByFqn(fqn) {
  selectedFqn.value = fqn
  try {
    const entity = await getEntity(fqn)
    detailEntity.value = entity

    if (entity.entity_type === 'TABLE' || entity.entity_type === 'VIEW') {
      selectedEntity.value = entity
      columnsLoading.value = true
      try {
        const children = await getEntityChildren(fqn)
        columns.value = children.filter(c => c.entity_type === 'COLUMN')
      } finally {
        columnsLoading.value = false
      }
    } else if (entity.entity_type === 'COLUMN') {
      const parentFqn = fqn.split('.').slice(0, -1).join('.')
      selectedEntity.value = { fqn: parentFqn, entity_type: 'TABLE' }
      selectedColumnFqn.value = fqn
      columnsLoading.value = true
      try {
        const children = await getEntityChildren(parentFqn)
        columns.value = children.filter(c => c.entity_type === 'COLUMN')
      } finally {
        columnsLoading.value = false
      }
    }
  } catch {
    detailEntity.value = null
  }
}
</script>

<style scoped>
.browse-layout { display: flex; height: 100%; }
.sidebar {
  width: var(--sidebar-width); background: var(--surface);
  border-right: 1px solid var(--border); display: flex;
  flex-direction: column; overflow: hidden;
}
.sidebar-header { padding: 16px; border-bottom: 1px solid var(--border); }
.sidebar-header h3 {
  font-size: 14px; font-weight: 600; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.5px;
}
.tree-container { flex: 1; overflow-y: auto; padding: 8px; }
.tree-item {
  display: flex; align-items: center; gap: 4px; padding: 6px 8px;
  border-radius: 6px; cursor: pointer; font-size: 13px;
}
.tree-item:hover { background: var(--background); }
.tree-item.selected { background: #e8f0fe; color: var(--primary); }
.expand-icon { font-size: 18px; color: var(--text-secondary); }
.node-icon { font-size: 16px; color: var(--text-secondary); }
.node-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.type-badge {
  font-size: 10px; padding: 1px 5px; border-radius: 4px;
  background: var(--background); color: var(--text-secondary); font-weight: 500;
}
.tree-child { padding-left: 24px; }
.child-item { padding: 4px 8px; }
.loading, .loading-child {
  padding: 12px; color: var(--text-secondary); font-style: italic; font-size: 13px;
}

/* Columns panel */
.columns-panel {
  width: 240px; background: var(--surface);
  border-right: 1px solid var(--border); display: flex;
  flex-direction: column; overflow: hidden;
  transition: width 0.2s ease;
}
.columns-panel.collapsed {
  width: 40px;
}
.columns-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 12px; border-bottom: 1px solid var(--border);
  min-height: 49px;
}
.columns-header h3 {
  font-size: 13px; font-weight: 600; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.5px;
  white-space: nowrap;
}
.collapse-btn {
  background: none; border: none; color: var(--text-secondary);
  display: flex; align-items: center; padding: 2px; border-radius: 4px;
}
.collapse-btn:hover { background: var(--background); }
.columns-list { flex: 1; overflow-y: auto; padding: 4px; }
.column-item {
  display: flex; align-items: center; gap: 6px; padding: 6px 8px;
  border-radius: 6px; cursor: pointer; font-size: 13px;
}
.column-item:hover { background: var(--background); }
.column-item.selected { background: #e8f0fe; color: var(--primary); }
.col-icon { font-size: 14px; color: var(--text-secondary); }
.col-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.col-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 500; }
.col-type { font-size: 10px; color: var(--text-secondary); font-family: monospace; }
.col-badge {
  font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 8px;
  min-width: 20px; text-align: center;
}
.col-badge.phi { background: #fce8e6; color: #c5221f; }
.col-badge.pii { background: #fef7e0; color: #e37400; }

.center-panel {
  flex: 1; overflow-y: auto; padding: 24px;
  display: flex; flex-direction: column; gap: 20px;
}
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 12px; padding: 60px; color: var(--text-secondary);
}
.empty-state .material-icons { font-size: 48px; opacity: 0.4; }
</style>
