// ============================================================
// 文件功能：日期/时间格式化工具
// 说明：
//   1. 后端所有时间字段（created_at / updated_at）存的是**UTC**
//      （`datetime.now(timezone.utc).replace(tzinfo=None)`），
//      但返回的 ISO 字符串**不带时区后缀**，前端无法自动识别时区
//   2. 业务场景：东八区运营/客服查看 → 需把 UTC 转换为北京时间显示
//   3. 实现：在 ISO 字符串末尾补 "Z"（= UTC 后缀），
//      new Date() 自动解析，再用 Intl.DateTimeFormat 显式格式化
//   4. 输出格式固定 `YYYY-MM-DD HH:mm:ss`（避免 zh-CN toLocaleString 在
//      不同 Node/浏览器下格式不一致：可能是 `/` 也可能是 `-`）
// ============================================================

const SHANGHAI_TZ = 'Asia/Shanghai'

/**
 * 把后端返回的 UTC ISO 时间字符串格式化为北京时间字符串
 *
 * @param iso 后端原始时间字符串（naive ISO："2026-08-27T15:00:44.573023"）
 * @param opts 选项：'datetime'（默认，YYYY-MM-DD HH:mm:ss）/ 'date'（仅日期）/ 'short'（MM-DD HH:mm）
 * @returns 北京时间格式化字符串（固定 "YYYY-MM-DD HH:mm:ss" 形式）
 */
export function formatDateTime(
  iso: string | null | undefined,
  opts: 'datetime' | 'date' | 'short' = 'datetime',
): string {
  if (!iso) return '-'
  try {
    // 后端返回的字符串无时区后缀，补 "Z" 明确为 UTC
    const utcIso = iso.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`
    const d = new Date(utcIso)
    if (Number.isNaN(d.getTime())) return iso

    // 用 Intl 拆出年月日时分秒（按上海时区），再手动拼成固定格式
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: SHANGHAI_TZ,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false,
    }).formatToParts(d)
    const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''

    if (opts === 'date') {
      return `${get('year')}-${get('month')}-${get('day')}`
    }
    if (opts === 'short') {
      return `${get('month')}-${get('day')} ${get('hour')}:${get('minute')}`
    }
    return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}:${get('second')}`
  } catch {
    return iso
  }
}
