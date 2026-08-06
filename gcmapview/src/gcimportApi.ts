const defaultApiBaseUrl = '/gcimport-api'

export const gcimportApiBaseUrl = (
  import.meta.env.VITE_GCIMPORT_API_URL ?? defaultApiBaseUrl
).replace(/\/$/, '')

export type ImportResult = {
  total: number
  features: Array<{
    collection: string
    id: string
  }>
}

function errorMessage(body: unknown, status: number) {
  if (
    typeof body === 'object' &&
    body !== null &&
    'detail' in body
  ) {
    const detail = body.detail
    if (typeof detail === 'string') return detail
    if (typeof detail === 'object' && detail !== null) {
      if ('message' in detail && typeof detail.message === 'string') {
        if ('errors' in detail && Array.isArray(detail.errors)) {
          return `${detail.message}: ${detail.errors.join('; ')}`
        }
        if ('reason' in detail && typeof detail.reason === 'string') {
          return `${detail.message}: ${detail.reason}`
        }
        return detail.message
      }
    }
  }
  return `Import failed with HTTP ${status}`
}

export async function uploadJsonFg(file: File): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${gcimportApiBaseUrl}/imports`, {
    method: 'POST',
    body: form,
  })

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(errorMessage(body, response.status))
  }
  return body as ImportResult
}
