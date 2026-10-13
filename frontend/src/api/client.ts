/** API 客户端：开发态走 Vite 代理，也可设 VITE_API_BASE 直连后端。 */
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

async function parseError(res: Response): Promise<string> {
  try {
    const j = (await res.json()) as { detail?: string; message?: string }
    return j.detail || j.message || res.statusText
  } catch {
    return res.statusText
  }
}

export async function api(path: string, options: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, options)
  if (!res.ok) {
    throw new Error(await parseError(res))
  }
  return res
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}
