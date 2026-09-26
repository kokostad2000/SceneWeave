/**
 * Unicode 码点计数工具。
 *
 * 后端使用 Python `len()`（码点）校验长度；JS 的 `string.length` 是 UTF-16 码元
 * 数量，emoji 等字符会被算成 2。这里统一按码点计数，避免前后端校验不一致
 * （PRD 3.3）。
 */

/** 返回字符串的 Unicode 码点数量，等价于后端 `codepoint_length()`。 */
export function codepointLength(value: string): number {
  return [...value].length
}

/** 先裁剪首尾空白，再返回码点数量（与后端校验顺序一致）。 */
export function trimmedCodepointLength(value: string): number {
  return codepointLength(value.trim())
}

/** 裁剪空白后是否落在 [min, max] 码点范围内。 */
export function isWithinCodepointLimit(value: string, min: number, max: number): boolean {
  const length = trimmedCodepointLength(value)
  return length >= min && length <= max
}
