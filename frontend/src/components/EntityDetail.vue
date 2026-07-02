<template>
  <div v-if="entity" class="detail-card">
    <div class="detail-header">
      <span class="material-icons entity-icon">{{ getIcon(entity.entity_type) }}</span>
      <div>
        <h2>{{ entity.name }}</h2>
        <span class="fqn">{{ entity.fqn }}</span>
      </div>
      <span class="entity-type-badge">{{ entity.entity_type }}</span>
    </div>

    <!-- Description -->
    <div class="section">
      <h4>Description</h4>
      <div v-if="editingDescription" class="desc-edit">
        <textarea v-model="descriptionDraft" rows="3"></textarea>
        <div class="desc-actions">
          <button class="btn btn-primary btn-sm" @click="saveDescription">Save</button>
          <button class="btn btn-secondary btn-sm" @click="editingDescription = false">Cancel</button>
        </div>
      </div>
      <p v-else class="description" @click="startEditDescription">
        {{ entity.description || 'Click to add description...' }}
      </p>
    </div>

    <!-- Metadata -->
    <div v-if="entity.metadata && Object.keys(entity.metadata).length > 0" class="section">
      <h4>Metadata</h4>
      <div class="metadata-grid">
        <div v-for="key in Object.keys(entity.metadata)" :key="key" class="meta-item">
          <span class="meta-key">{{ key }}</span>
          <span class="meta-value">{{ entity.metadata[key] }}</span>
        </div>
      </div>
    </div>

    <!-- Tags -->
    <div class="section">
      <h4>Tags</h4>
      <div class="tags-list">
        <span v-for="tag in entity.tags" :key="tag.id" class="tag">
          {{ tag.key }}{{ tag.value ? '=' + tag.value : '' }}
          <button class="tag-remove" @click="handleRemoveTag(tag)">×</button>
        </span>
        <div class="tag-add">
          <input
            type="text" placeholder="key=value"
            v-model="newTag" @keyup.enter="handleAddTag"
            class="tag-input">
          <button class="btn btn-secondary btn-sm" @click="handleAddTag">Add</button>
        </div>
      </div>
    </div>

    <!-- Terms -->
    <div v-if="entity.terms && entity.terms.length > 0" class="section">
      <h4>Terms</h4>
      <div class="terms-list">
        <div v-for="term in entity.terms" :key="term.id" class="term-item">
          <span :class="'badge badge-' + term.term_type">{{ term.term_type }}</span>
          <span class="term-name">{{ term.term_name }}</span>
          <span class="term-score">{{ term.score }}</span>
        </div>
      </div>
    </div>

    <!-- PHI/PII -->
    <div v-if="phiInfo" class="section">
      <h4>Identifiable Information</h4>
      <div class="phi-scores">
        <div class="score-item">
          <span class="score-label">PHI Score</span>
          <div class="score-bar"><div class="score-fill phi-fill" :style="{ width: phiInfo.info.phi_score + '%' }"></div></div>
          <span class="score-value">{{ phiInfo.info.phi_score }}</span>
        </div>
        <div class="score-item">
          <span class="score-label">PII Score</span>
          <div class="score-bar"><div class="score-fill pii-fill" :style="{ width: phiInfo.info.pii_score + '%' }"></div></div>
          <span class="score-value">{{ phiInfo.info.pii_score }}</span>
        </div>
      </div>
      <div v-if="phiInfo.boosters.length > 0" class="boosters">
        <h5>Boosters ({{ phiInfo.boosters.length }})</h5>
        <div v-for="b in phiInfo.boosters" :key="b.secondary_entity_fqn + b.boost_type" class="booster-item">
          <span class="booster-type">{{ b.boost_type }}</span>
          <span class="booster-fqn">{{ b.secondary_entity_fqn }}</span>
          <span class="booster-score">+{{ b.boost_score }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { getPhiInfo, addTag, removeTag, updateDescription } from '../services/api.js'

const props = defineProps({ entity: Object })

const phiInfo = ref(null)
const editingDescription = ref(false)
const descriptionDraft = ref('')
const newTag = ref('')

watch(() => props.entity, async (entity) => {
  if (!entity) return
  editingDescription.value = false
  phiInfo.value = null
  try {
    phiInfo.value = await getPhiInfo(entity.fqn)
  } catch { /* ignore */ }
}, { immediate: true })

function getIcon(type) {
  const icons = { DATABASE: 'storage', SCHEMA: 'folder', TABLE: 'table_chart', VIEW: 'view_list', COLUMN: 'view_column' }
  return icons[type] || 'article'
}

function startEditDescription() {
  descriptionDraft.value = props.entity.description || ''
  editingDescription.value = true
}

async function saveDescription() {
  const res = await updateDescription(props.entity.fqn, descriptionDraft.value)
  props.entity.description = res.description
  editingDescription.value = false
}

async function handleAddTag() {
  if (!newTag.value.trim()) return
  const parts = newTag.value.split('=', 2)
  const key = parts[0].trim()
  const value = parts.length > 1 ? parts[1].trim() : ''
  if (!key) return
  const tag = await addTag(props.entity.fqn, key, value)
  props.entity.tags.push(tag)
  newTag.value = ''
}

async function handleRemoveTag(tag) {
  await removeTag(props.entity.fqn, tag.id)
  props.entity.tags = props.entity.tags.filter(t => t.id !== tag.id)
}
</script>

<style scoped>
.detail-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; }
.detail-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
.entity-icon { font-size: 32px; color: var(--primary); }
.detail-header h2 { font-size: 20px; font-weight: 600; }
.fqn { font-size: 12px; color: var(--text-secondary); font-family: monospace; }
.entity-type-badge { margin-left: auto; padding: 4px 10px; border-radius: 6px; background: #e8f0fe; color: var(--primary); font-size: 12px; font-weight: 500; }
.section { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border); }
.section h4 { font-size: 13px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }
.description { cursor: pointer; padding: 8px; border-radius: 6px; }
.description:hover { background: var(--background); }
.desc-edit textarea { width: 100%; border: 1px solid var(--border); border-radius: 6px; padding: 8px; font-family: inherit; resize: vertical; }
.desc-actions { display: flex; gap: 8px; margin-top: 8px; }
.metadata-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.meta-item { display: flex; flex-direction: column; padding: 8px; background: var(--background); border-radius: 6px; }
.meta-key { font-size: 11px; color: var(--text-secondary); font-weight: 500; text-transform: uppercase; }
.meta-value { font-size: 13px; font-family: monospace; }
.tags-list { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.tag { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; background: #e8f5e9; color: var(--success); border-radius: 16px; font-size: 12px; font-weight: 500; }
.tag-remove { background: none; border: none; color: inherit; font-size: 16px; cursor: pointer; padding: 0 2px; }
.tag-add { display: flex; gap: 4px; }
.tag-input { width: 140px; font-size: 12px; padding: 4px 8px; }
.terms-list { display: flex; flex-direction: column; gap: 4px; }
.term-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.term-name { flex: 1; font-family: monospace; font-size: 13px; }
.term-score { font-weight: 600; font-size: 13px; color: var(--text-secondary); }
.phi-scores { display: flex; flex-direction: column; gap: 12px; }
.score-item { display: flex; align-items: center; gap: 12px; }
.score-label { width: 80px; font-size: 13px; font-weight: 500; }
.score-bar { flex: 1; height: 8px; background: var(--background); border-radius: 4px; overflow: hidden; }
.score-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.phi-fill { background: var(--error); }
.pii-fill { background: var(--warning); }
.score-value { width: 30px; text-align: right; font-weight: 600; font-size: 13px; }
.boosters { margin-top: 12px; }
.boosters h5 { font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }
.booster-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 12px; }
.booster-type { padding: 2px 6px; background: var(--background); border-radius: 4px; font-size: 11px; }
.booster-fqn { flex: 1; font-family: monospace; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.booster-score { font-weight: 600; color: var(--success); }
</style>
