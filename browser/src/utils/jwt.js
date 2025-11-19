export function isTokenValid(token) {
  if (!token) return false
  try {
    const payload = JSON.parse(atob(token.split('.')[1])) // 解析 JWT payload
    if (!payload.exp) return true
    return Date.now() / 1000 < payload.exp         // 未过期
  } catch {
    return false
  }
}
