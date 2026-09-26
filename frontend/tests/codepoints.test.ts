import { describe, expect, it } from 'vitest'

import { codepointLength, isWithinCodepointLimit, trimmedCodepointLength } from '../src/lib/codepoints'

describe('Unicode 码点计数', () => {
  it('按码点而不是 UTF-16 码元计数', () => {
    const emoji = '😀'

    expect(codepointLength(emoji)).toBe(1)
    // 这正是不能直接用 string.length 的原因。
    expect(emoji.length).toBe(2)
  })

  it('与后端一致地处理中日韩文本与 emoji 混合', () => {
    expect(codepointLength('安然')).toBe(2)
    expect(codepointLength('安然😀')).toBe(3)
    expect(codepointLength('')).toBe(0)
  })

  it('先裁剪空白再计数', () => {
    expect(trimmedCodepointLength('   你好   ')).toBe(2)
    expect(trimmedCodepointLength('   ')).toBe(0)
  })

  it('对 200 码点的发言上限给出与后端相同的判断', () => {
    // 后端 MAX_SPEAK_TEXT_CODEPOINTS = 200：200 合法、201 非法。
    expect(isWithinCodepointLimit('😀'.repeat(200), 1, 200)).toBe(true)
    expect(isWithinCodepointLimit('😀'.repeat(201), 1, 200)).toBe(false)
    expect(isWithinCodepointLimit('   ', 1, 200)).toBe(false)
  })
})
