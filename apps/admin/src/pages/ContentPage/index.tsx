// ============================================================
// 文件功能：内容管理（UI-UX §6.6，PRD F13）
// 说明：
//   1. 两列卡片网格，9 张内容卡（硬件+软件合并为一张）
//   2. 保存后前台实时生效（前端每次进页面重新拉取）
//   3. Banner 卡支持子管理（新增/编辑/删除，≤4 张）
//   4. 富文本（brand_story 等）存 Markdown，textarea 编辑
// ============================================================

import { useCallback, useEffect, useState } from 'react'
import { client } from '@/api/client'
import type { BannerItem, ContentKeyItem } from '@/api/types'
import { PageHeader, Modal, Toast, Spinner } from '@/components/AdminComponents'
import { Button, FormField, Upload } from '@/components/AdminForm'
import styles from './ContentPage.module.css'

// 内容卡配置：key / 标题 / 说明 / 编辑类型
const CARDS: { key: string; no: string; title: string; desc: string; type: 'banners' | 'markdown' | 'chars' | 'journey' | 'hs' | 'order' | 'contact' }[] = [
  { key: 'banners', no: '01', title: 'Banner 轮播图', desc: '首页主视觉，支持 1–4 张', type: 'banners' },
  { key: 'brand_story', no: '02', title: '品牌故事', desc: '富文本 + 图片（Markdown）', type: 'markdown' },
  { key: 'brand_value', no: '03', title: '品牌理念', desc: '富文本（Markdown）', type: 'markdown' },
  { key: 'brand_chars', no: '04', title: '品牌特色', desc: '卡片条目（标题/描述）', type: 'chars' },
  { key: 'brand_journey', no: '05', title: '品牌历程', desc: '时间线条目（年份/标题/描述）', type: 'journey' },
  { key: 'hs', no: '06', title: '硬件保障 & 软件实力', desc: '列表条目（名称/描述）', type: 'hs' },
  { key: 'order_info', no: '07', title: '订购信息', desc: '专线/服务时间/配送说明（前台页脚与订购区共用）', type: 'order' },
  { key: 'contact_info', no: '08', title: '联系我们', desc: '地址/邮箱（专线、时间复用 07）', type: 'contact' },
  { key: 'custom_tips', no: '09', title: '定制说明', desc: '蛋糕详情页定制说明文案', type: 'markdown' },
]

// 卡片标题展示用的短名
const CARD_SHORT: Record<string, string> = {
  banners: 'Banner', brand_story: '品牌故事', brand_value: '品牌理念', brand_chars: '品牌特色',
  brand_journey: '品牌历程', hs: '硬件软件', order_info: '订购信息', contact_info: '联系我们', custom_tips: '定制说明',
}

export default function ContentPage() {
  const [keys, setKeys] = useState<ContentKeyItem[]>([])
  const [loading, setLoading] = useState(true)
  // 编辑弹窗状态
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  function showToast(type: 'success' | 'error', text: string) {
    setToast({ type, text })
    setTimeout(() => setToast(null), 4000)
  }

  // 加载内容 key 列表（updated_at 用于状态徽章）
  const loadKeys = useCallback(() => {
    client.get('/content')
      .then((r) => setKeys(r.data.data.items as ContentKeyItem[]))
      .catch(() => setKeys([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadKeys() }, [loadKeys])

  // 各 key 是否已编辑过
  function updatedAt(key: string): string | null {
    return keys.find((k) => k.key === key)?.updated_at ?? null
  }

  return (
    <div>
      <PageHeader meta="CONTENT · 内容管理" title="内容管理" />

      {loading ? <Spinner text="内容加载中…" /> : (
        <div className={styles.grid}>
          {CARDS.map((card) => {
            const up = updatedAt(card.key) ?? updatedAt(card.key === 'hs' ? 'hardware' : '') ?? null
            return (
              <div key={card.key} className={styles.card}>
                <div className={styles.cardHead}>
                  <span className={styles.cardNo}>{card.no}</span>
                  <div className={styles.cardTitleWrap}>
                    <h3 className={styles.cardTitle}>{card.title}</h3>
                    <p className={styles.cardDesc}>{card.desc}</p>
                  </div>
                  {/* 状态徽章：已更新 / 未编辑 */}
                  <span className={`${styles.badge} ${up ? styles.badgeDone : styles.badgeNew}`}>
                    {up ? '已更新' : '未编辑'}
                  </span>
                </div>
                <div className={styles.cardActions}>
                  {card.type === 'banners' && (
                    <Button size="sm" onClick={() => setEditingKey('banners')}>编辑 / 管理</Button>
                  )}
                  {card.type !== 'banners' && (
                    <Button size="sm" onClick={() => setEditingKey(card.key)}>编辑</Button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 编辑弹窗：按内容类型渲染不同表单 */}
      {editingKey && (
        <ContentEditor
          key={editingKey}
          contentKey={editingKey}
          onClose={() => setEditingKey(null)}
          onSaved={() => { setEditingKey(null); loadKeys(); showToast('success', '内容已保存，前台实时生效') }}
          onToast={(t) => showToast(t.type, t.text)}
        />
      )}

      <Toast toast={toast} />
    </div>
  )
}

// ============================================================
// 内容编辑器：按类型渲染（banners / markdown / chars / journey / hs / order / contact）
// ============================================================
function ContentEditor({ contentKey, onClose, onSaved, onToast }: {
  contentKey: string
  onClose: () => void
  onSaved: () => void
  onToast: (t: { type: 'success' | 'error'; text: string }) => void
}) {
  const [value, setValue] = useState<unknown>(null)
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // 读取内容
  useEffect(() => {
    setLoaded(false)
    setError('')
    if (contentKey === 'hs') {
      // 硬件 + 软件是**两个独立的 key**，需并发拉取（不能从 hardware 响应里读 software）
      Promise.all([
        client.get('/content/hardware').then((r) => (r.data.data as { value: { name: string; desc: string }[] }).value ?? []),
        client.get('/content/software').then((r) => (r.data.data as { value: { name: string; desc: string }[] }).value ?? []),
      ])
        .then(([hardware, software]) => {
          setValue({ hardware, software })
          setLoaded(true)
        })
        .catch((e) => { setError((e as Error).message); setLoaded(true) })
      return
    }
    const realKey = contentKey
    client.get(`/content/${realKey}`)
      .then((r) => {
        const v = (r.data.data as { value: unknown }).value
        setValue(v)
        setLoaded(true)
      })
      .catch((e) => { setError((e as Error).message); setLoaded(true) })
  }, [contentKey])

  // 保存
  async function submit() {
    if (saving) return
    setSaving(true)
    try {
      if (contentKey === 'banners') {
        await client.put('/content/banners', { value: value as unknown })
      } else if (contentKey === 'hs') {
        const v = value as { hardware: { name: string; desc: string }[]; software: { name: string; desc: string }[] }
        await client.put('/content/hardware', { value: v.hardware })
        await client.put('/content/software', { value: v.software })
      } else {
        await client.put(`/content/${contentKey}`, { value: value as unknown })
      }
      onSaved()
    } catch (e) {
      onToast({ type: 'error', text: (e as Error).message })
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) return <Modal open title={CARD_SHORT[contentKey]} onClose={onClose}><Spinner text="内容加载中…" /></Modal>
  if (error) return <Modal open title={CARD_SHORT[contentKey]} onClose={onClose}><p style={{ color: 'var(--danger)' }}>{error}</p></Modal>

  return (
    <Modal open title={CARD_SHORT[contentKey]} onClose={onClose} width={720}
      footer={<>
        <Button variant="ghost" onClick={onClose}>取消</Button>
        <Button onClick={submit} disabled={saving}>{saving ? '保存中…' : '保存并生效'}</Button>
      </>}>
      {/* Banner 管理 */}
      {contentKey === 'banners' && <BannerEditor value={(value as { banners: BannerItem[] })?.banners ?? []} onChange={(b) => setValue({ banners: b })} />}

      {/* Markdown 富文本 */}
      {contentKey === 'brand_story' && <MdEditor value={String(value ?? '')} onChange={(v) => setValue(v)} />}
      {contentKey === 'brand_value' && <MdEditor value={String(value ?? '')} onChange={(v) => setValue(v)} />}
      {contentKey === 'custom_tips' && <MdEditor value={String(value ?? '')} onChange={(v) => setValue(v)} />}

      {/* 品牌特色：标题 + 描述 条目 */}
      {contentKey === 'brand_chars' && (
        <ItemListEditor
          fields={[{ key: 'title', label: '标题', placeholder: '如：甄选食材' }, { key: 'desc', label: '描述', placeholder: '一句话说明' }]}
          items={(value as { brand_chars: { title: string; desc: string }[] })?.brand_chars ?? []}
          onChange={(items) => setValue({ brand_chars: items })}
        />
      )}

      {/* 品牌历程：年份 + 标题 + 描述 */}
      {contentKey === 'brand_journey' && (
        <ItemListEditor
          fields={[{ key: 'year', label: '年份', placeholder: '如：2020' }, { key: 'title', label: '标题', placeholder: '如：品牌诞生' }, { key: 'desc', label: '描述', placeholder: '一句话说明' }]}
          items={(value as { brand_journey: { year: string; title: string; desc: string }[] })?.brand_journey ?? []}
          onChange={(items) => setValue({ brand_journey: items })}
        />
      )}

      {/* 硬件 + 软件 */}
      {contentKey === 'hs' && (
        <div>
          <h4 className={styles.subTitle}>硬件保障</h4>
          <ItemListEditor
            fields={[{ key: 'name', label: '名称', placeholder: '如：中央冷链配送' }, { key: 'desc', label: '描述', placeholder: '一句话说明' }]}
            items={(value as { hardware: { name: string; desc: string }[] }).hardware}
            onChange={(items) => setValue((prev: unknown) => ({ ...(prev as object), hardware: items }))}
          />
          <h4 className={styles.subTitle}>软件实力</h4>
          <ItemListEditor
            fields={[{ key: 'name', label: '名称', placeholder: '如：专业烘焙团队' }, { key: 'desc', label: '描述', placeholder: '一句话说明' }]}
            items={(value as { software: { name: string; desc: string }[] }).software}
            onChange={(items) => setValue((prev: unknown) => ({ ...(prev as object), software: items }))}
          />
        </div>
      )}

      {/* 订购信息：3 字段 */}
      {contentKey === 'order_info' && (
        <div className={styles.formCol}>
          <FormField label="订购专线">
            <input className={styles.input} value={(value as { hotline: string }).hotline ?? ''}
              onChange={(e) => setValue({ ...(value as object), hotline: e.target.value })} placeholder="如：021-XXXXXXX" />
          </FormField>
          <FormField label="服务时间">
            <input className={styles.input} value={(value as { hours: string }).hours ?? ''}
              onChange={(e) => setValue({ ...(value as object), hours: e.target.value })} placeholder="如：08:00-18:00" />
          </FormField>
          <FormField label="配送说明">
            <input className={styles.input} value={(value as { delivery_note: string }).delivery_note ?? ''}
              onChange={(e) => setValue({ ...(value as object), delivery_note: e.target.value })} placeholder="如：11 点前订购当日送达" />
          </FormField>
        </div>
      )}

      {/* 联系我们：2 字段 */}
      {contentKey === 'contact_info' && (
        <div className={styles.formCol}>
          <FormField label="总部地址">
            <input className={styles.input} value={(value as { address: string }).address ?? ''}
              onChange={(e) => setValue({ ...(value as object), address: e.target.value })} />
          </FormField>
          <FormField label="邮箱">
            <input className={styles.input} value={(value as { email: string }).email ?? ''}
              onChange={(e) => setValue({ ...(value as object), email: e.target.value })} />
          </FormField>
        </div>
      )}
    </Modal>
  )
}

// ---------- Markdown 编辑器 ----------
function MdEditor({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <p className={styles.help}>支持 Markdown 语法（# 标题、**加粗**、- 列表等），保存后前台实时生效</p>
      <textarea className={`${styles.input} ${styles.mdArea}`} rows={12} value={value}
        maxLength={20000} onChange={(e) => onChange(e.target.value)} />
      <p className={styles.count}>{value.length}/20000</p>
    </div>
  )
}

// ---------- Banner 管理（子管理：新增/编辑/删除，≤4） ----------
function BannerEditor({ value, onChange }: { value: BannerItem[]; onChange: (b: BannerItem[]) => void }) {
  function update(i: number, field: keyof BannerItem, v: string | boolean) {
    onChange(value.map((b, idx) => (idx === i ? { ...b, [field]: v } : b)))
  }
  function remove(i: number) { onChange(value.filter((_, idx) => idx !== i)) }
  function add() {
    if (value.length >= 4) return
    onChange([...value, { id: Date.now(), image_url: '', slogan: '', subtitle: '', sort_order: value.length + 1, is_active: true }])
  }

  return (
    <div>
      <p className={styles.help}>首页 Hero 轮播（1–4 张）；图片建议 1600×900；slogan 为图上大标题文案</p>
      {value.length === 0 && <p className={styles.emptyHint}>暂无 Banner，点击下方"新增"添加（前台会隐藏该区块）</p>}
      {value.map((b, i) => (
        <div key={b.id} className={styles.bannerRow}>
          <span className={styles.bannerIndex}>#{i + 1}</span>
          <div className={styles.bannerFields}>
            <Upload value={b.image_url} onChange={(url) => update(i, 'image_url', url)} dir="banners" />
            <div className={styles.bannerText}>
              <FormField label="Slogan（大标题）">
                <input className={styles.input} value={b.slogan ?? ''} maxLength={40}
                  onChange={(e) => update(i, 'slogan', e.target.value)} placeholder="如：麦屿手作，手作每一份甜蜜" />
              </FormField>
              <FormField label="副文案">
                <input className={styles.input} value={b.subtitle ?? ''} maxLength={60}
                  onChange={(e) => update(i, 'subtitle', e.target.value)} placeholder="如：EST. 2020 SHANGHAI" />
              </FormField>
            </div>
          </div>
          <button type="button" className={styles.bannerDel} onClick={() => remove(i)} aria-label="删除该 Banner">×</button>
        </div>
      ))}
      <Button variant="ghost" onClick={add} disabled={value.length >= 4} size="sm">＋ 新增 Banner</Button>
      {value.length >= 4 && <span className={styles.help}>最多 4 张（PRD v2.3）</span>}
    </div>
  )
}

// ---------- 条目列表编辑器（品牌特色/历程/硬件软件） ----------
function ItemListEditor({ fields, items, onChange }: {
  fields: { key: string; label: string; placeholder: string }[]
  items: Record<string, string>[]
  onChange: (items: Record<string, string>[]) => void
}) {
  function update(i: number, key: string, v: string) {
    onChange(items.map((it, idx) => (idx === i ? { ...it, [key]: v } : it)))
  }
  function remove(i: number) { onChange(items.filter((_, idx) => idx !== i)) }
  function add() {
    const empty: Record<string, string> = {}
    fields.forEach((f) => { empty[f.key] = '' })
    onChange([...items, empty])
  }

  return (
    <div>
      {items.map((it, i) => (
        <div key={i} className={styles.itemRow}>
          <div className={styles.itemFields}>
            {fields.map((f) => (
              <FormField key={f.key} label={f.label}>
                <input className={styles.input} value={it[f.key] ?? ''} placeholder={f.placeholder}
                  onChange={(e) => update(i, f.key, e.target.value)} />
              </FormField>
            ))}
          </div>
          <button type="button" className={styles.itemDel} onClick={() => remove(i)} aria-label="删除该条">×</button>
        </div>
      ))}
      <Button variant="ghost" onClick={add} size="sm">＋ 新增一条</Button>
    </div>
  )
}
