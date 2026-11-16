const BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "")

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json", ...(options.headers || {}) },
    ...options,
  })

  if (!res.ok) {
    let detail = ""
    try {
      const body = await res.json()
      detail = body.detail || ""
    } catch {
      detail = await res.text().catch(() => "")
    }
    throw new Error(`HTTP ${res.status}${detail ? `: ${detail}` : ""}`)
  }

  if (res.status === 204) return null
  return res.json()
}

export const api = {
  listChats: () => request("/api/chats"),
  createChat: (title = "Новый диалог") =>
    request("/api/chats", { method: "POST", body: JSON.stringify({ title }) }),
  deleteChat: (id) => request(`/api/chats/${id}`, { method: "DELETE" }),
  listMessages: (chatId) => request(`/api/chats/${chatId}/messages`),
  sendMessage: (chatId, text) =>
    request(`/api/chats/${chatId}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
}