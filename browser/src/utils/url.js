// 统一资源 URL：支持后端返回相对路径 /files/...，也兼容完整的 http(s) 链接
export function toDisplayUrl(path = '') {
  if (!path) return ''
  const str = String(path).trim()
  if (/^https?:\/\//i.test(str)) return str
  if (str.startsWith('//')) return `${window?.location?.protocol || 'http:'}${str}`
  return str.startsWith('/') ? str : `/${str}`
}
