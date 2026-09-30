/** 仅保存视图选择 ID，不保存正文、提示词或私有资料。 */
export function readView<T>(key: string, fallback: T): T {
  try { return JSON.parse(sessionStorage.getItem(`sceneweave:${key}`) ?? 'null') as T ?? fallback } catch { return fallback }
}
export function saveView(key: string, value: unknown): void {
  try { sessionStorage.setItem(`sceneweave:${key}`, JSON.stringify(value)) } catch { /* 禁用存储仍可使用当前视图 */ }
}
