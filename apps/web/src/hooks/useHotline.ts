// ============================================================
// 文件功能：订购号码 Hook（专属号优先，内容号兜底）
//
// 为什么需要这一层：
//   「官网专属号码」是归因链路能成立的唯一锚点——不同渠道的访客必须看到
//   不同号码，电话那头才知道这通电话从哪来。但前台原来的号码直接来自
//   content.order_info（所有人看到同一个号），等于归因永远只能靠手机号碰运气。
//
// 三层取值，优先级从高到低：
//   ① /track/hotline 按访客渠道下发的专属号（有归因价值）
//   ② content.order_info 里的订购专线（运营在后台维护的兜底）
//   ③ 调用方传入的硬编码兜底（最后保险，避免页面上电话变成空白）
//
// ⚠️ 任何一层都不能让「电话显示为空」：埋点接口挂了顶多是归因不准，
//    电话显示不出来是直接把生意挡掉，两者严重程度完全不同。
// ============================================================

import { useEffect, useState } from 'react'
import { fetchHotline } from '@/utils/tracker'

export interface HotlineResult {
  phone: string
  /** 号码来源：tracking=渠道专属号，content=后台订购信息，fallback=硬编码兜底 */
  source: 'tracking' | 'content' | 'fallback'
  label: string
}

export function useHotline(
  contentHotline?: string,
  hardFallback = '021-XXXXXXX'
): HotlineResult {
  const [state, setState] = useState<HotlineResult>({
    phone: (contentHotline || '').trim() || hardFallback,
    source: (contentHotline || '').trim() ? 'content' : 'fallback',
    label: '订购热线',
  })

  useEffect(() => {
    let alive = true
    fetchHotline()
      .then((info) => {
        if (!alive) return
        if (info?.phone) {
          setState({ phone: info.phone, source: 'tracking', label: info.label })
        } else {
          // 专属号取不到 → 用后台维护的订购信息兜底
          const fallback = (contentHotline || '').trim()
          if (fallback) {
            setState({ phone: fallback, source: 'content', label: '订购热线' })
          }
        }
      })
      .catch(() => {
        /* 静默：保持当前兜底值 */
      })
    return () => {
      alive = false
    }
  }, [contentHotline])

  return state
}
