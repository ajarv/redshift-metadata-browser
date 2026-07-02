const BASE = '/api'

export async function getSchemas() {
  const res = await fetch(`${BASE}/schemas/`)
  return res.json()
}

export async function getSchemaChildren(schemaName) {
  const res = await fetch(`${BASE}/schemas/${schemaName}/children/`)
  return res.json()
}

export async function getEntity(fqn) {
  const res = await fetch(`${BASE}/entities/${fqn}/`)
  return res.json()
}

export async function getEntityChildren(fqn) {
  const res = await fetch(`${BASE}/entities/${fqn}/children/`)
  return res.json()
}

export async function searchEntities(query) {
  const res = await fetch(`${BASE}/search/?q=${encodeURIComponent(query)}`)
  return res.json()
}

export async function addTag(fqn, key, value = '') {
  const res = await fetch(`${BASE}/entities/${fqn}/tags/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, value }),
  })
  return res.json()
}

export async function removeTag(fqn, tagId) {
  await fetch(`${BASE}/entities/${fqn}/tags/${tagId}/`, { method: 'DELETE' })
}

export async function updateDescription(fqn, description) {
  const res = await fetch(`${BASE}/entities/${fqn}/description/`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description }),
  })
  return res.json()
}

export async function getPhiInfo(fqn) {
  const res = await fetch(`${BASE}/entities/${fqn}/phi/`)
  return res.json()
}

export async function getTasks() {
  const res = await fetch(`${BASE}/tasks/`)
  return res.json()
}

export async function runTask(request) {
  const res = await fetch(`${BASE}/tasks/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  return res.json()
}

export async function getTaskStatus(taskId) {
  const res = await fetch(`${BASE}/tasks/${taskId}/`)
  return res.json()
}
