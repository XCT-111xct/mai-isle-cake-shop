// ============================================================
// 文件功能：门店管理（UI-UX §6.5，PRD F12）
// 功能：列表 / 新增编辑弹窗 / 停用启用 / 删除
// ============================================================

import { useCallback, useEffect, useState } from 'react'
import { client } from '@/api/client'
import type { StoreRow, PageResult } from '@/api/types'
import {
  PageHeader, Table, Modal, Switch, StatusBadge, Pagination, Toast, Spinner,
} from '@/components/AdminComponents'
import { Button, FormField, Upload } from '@/components/AdminForm'
import styles from './StoreManagePage.module.css'

export default function StoreManagePage() {
  const [stores, setStores] = useState<StoreRow[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(12)
  const [loading, setLoading] = useState(true)

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<StoreRow | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  function showToast(type: 'success' | 'error', text: string) {
    setToast({ type, text })
    setTimeout(() => setToast(null), 4000)
  }

  const loadList = useCallback(() => {
    setLoading(true)
    client.get('/stores', { params: { page, page_size: pageSize } })
      .then((r) => {
        const d = r.data.data as PageResult<StoreRow>
        setStores(d.items); setTotal(d.total); setTotalPages(d.total_pages)
      })
      .catch(() => setStores([]))
      .finally(() => setLoading(false))
  }, [page, pageSize])

  useEffect(() => { loadList() }, [loadList])

  async function toggleActive(store: StoreRow) {
    try {
      await client.patch(`/stores/${store.id}/status`, { is_active: !store.is_active })
      showToast('success', store.is_active ? `「${store.name}」已停用（前台不再展示）` : `「${store.name}」已启用`)
      loadList()
    } catch (e) { showToast('error', (e as Error).message) }
  }

  async function remove(store: StoreRow) {
    if (!window.confirm(`确认删除门店「${store.name}」？此操作不可恢复`)) return
    try {
      await client.delete(`/stores/${store.id}`)
      showToast('success', '门店已删除')
      loadList()
    } catch (e) { showToast('error', (e as Error).message) }
  }

  function openCreate() { setEditing(null); setModalOpen(true) }
  function openEdit(store: StoreRow) { setEditing(store); setModalOpen(true) }

  return (
    <div>
      <PageHeader meta="STORES · 门店管理" title="门店管理"
        actions={<Button onClick={openCreate}>＋ 新增门店</Button>} />

      {loading ? <Spinner text="门店加载中…" /> : (
        <Table
          rowKey="id"
          data={stores as unknown as Record<string, unknown>[]}
          columns={[
            { key: 'id', title: 'ID', width: '60px', render: (r) => `#${r.id}` },
            { key: 'image_url', title: '门店图', render: (r) => (
                <img className={styles.thumb} src={(r.image_url as string) || '/placeholder-story.svg'} alt={String(r.name)} />
              ) },
            { key: 'name', title: '门店名称', render: (r) => <span className={styles.name}>{String(r.name)}</span> },
            { key: 'address', title: '地址', render: (r) => <span className={styles.addr}>{String(r.address)}</span> },
            { key: 'phone', title: '电话', render: (r) => String(r.phone) },
            { key: 'hours', title: '营业时间', render: (r) => String(r.hours ?? '—') },
            { key: 'sort_order', title: '排序', render: (r) => String(r.sort_order) },
            { key: 'is_active', title: '状态', render: (r) => <StatusBadge status={r.is_active ? 'active' : 'inactive'} /> },
            { key: 'ops', title: '操作', render: (r) => {
                const s = r as unknown as StoreRow
                return (
                  <div className={styles.ops}>
                    <Button variant="text" size="sm" onClick={() => openEdit(s)}>编辑</Button>
                    <Button variant="text" size="sm" onClick={() => toggleActive(s)}>{s.is_active ? '停用' : '启用'}</Button>
                    <Button variant="text" size="sm" onClick={() => remove(s)}>删除</Button>
                  </div>
                )
              } },
          ]}
        />
      )}

      <Pagination page={page} totalPages={totalPages} onChange={setPage} />

      <StoreModal open={modalOpen} onClose={() => setModalOpen(false)} editing={editing}
        onSaved={() => { setModalOpen(false); loadList() }} onToast={(t) => showToast(t.type, t.text)} />

      <Toast toast={toast} />
    </div>
  )
}

// ---------- 新增/编辑门店弹窗 ----------
function StoreModal({ open, onClose, editing, onSaved, onToast }: {
  open: boolean
  onClose: () => void
  editing: StoreRow | null
  onSaved: () => void
  onToast: (t: { type: 'success' | 'error'; text: string }) => void
}) {
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [phone, setPhone] = useState('')
  const [hours, setHours] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const [sortOrder, setSortOrder] = useState(1)
  const [isActive, setIsActive] = useState(true)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!open) return
    if (editing) {
      setName(editing.name); setAddress(editing.address); setPhone(editing.phone)
      setHours(editing.hours ?? ''); setImageUrl(editing.image_url ?? '')
      setSortOrder(editing.sort_order); setIsActive(editing.is_active)
    } else {
      setName(''); setAddress(''); setPhone(''); setHours(''); setImageUrl('')
      setSortOrder(1); setIsActive(true)
    }
    setErrors({})
  }, [open, editing])

  function validate(): boolean {
    const next: Record<string, string> = {}
    if (name.trim().length < 2 || name.trim().length > 30) next.name = '门店名称需为 2-30 个字符'
    if (!address.trim() || address.trim().length > 100) next.address = '地址不能为空且不超过 100 字'
    if (!phone.trim() || phone.trim().length > 20) next.phone = '电话不能为空且不超过 20 字'
    if (hours.length > 50) next.hours = '营业时间不超过 50 字'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function submit() {
    if (!validate() || saving) return
    setSaving(true)
    const payload = {
      name: name.trim(), address: address.trim(), phone: phone.trim(),
      hours: hours.trim() || undefined, image_url: imageUrl || undefined,
      sort_order: Number(sortOrder) || 1, is_active: isActive,
    }
    try {
      if (editing) {
        await client.put(`/stores/${editing.id}`, payload)
        onToast({ type: 'success', text: '门店已更新' })
      } else {
        await client.post('/stores', payload)
        onToast({ type: 'success', text: '门店已新增' })
      }
      onSaved()
    } catch (e) { onToast({ type: 'error', text: (e as Error).message }) }
    finally { setSaving(false) }
  }

  return (
    <Modal open={open} title={editing ? '编辑门店' : '新增门店'} onClose={onClose} width={600}
      footer={<>
        <Button variant="ghost" onClick={onClose}>取消</Button>
        <Button onClick={submit} disabled={saving}>{saving ? '保存中…' : '保存'}</Button>
      </>}>
      <div className={styles.formRow2}>
        <FormField label="门店名称" required error={errors.name}>
          <input className={`${styles.input} ${errors.name ? styles.inputError : ''}`} value={name} maxLength={30}
            onChange={(e) => { setName(e.target.value); if (errors.name) setErrors((p) => ({ ...p, name: '' })) }} placeholder="如：联洋店" />
        </FormField>
        <FormField label="联系电话" required error={errors.phone}>
          <input className={`${styles.input} ${errors.phone ? styles.inputError : ''}`} value={phone} maxLength={20}
            onChange={(e) => { setPhone(e.target.value); if (errors.phone) setErrors((p) => ({ ...p, phone: '' })) }} placeholder="如：021-58388761" />
        </FormField>
      </div>
      <FormField label="门店地址" required error={errors.address}>
        <input className={`${styles.input} ${errors.address ? styles.inputError : ''}`} value={address} maxLength={100}
          onChange={(e) => { setAddress(e.target.value); if (errors.address) setErrors((p) => ({ ...p, address: '' })) }} placeholder="详细地址" />
      </FormField>
      <div className={styles.formRow2}>
        <FormField label="营业时间" error={errors.hours} help="如：08:00-21:00">
          <input className={styles.input} value={hours} maxLength={50}
            onChange={(e) => setHours(e.target.value)} placeholder="如：08:00-21:00" />
        </FormField>
        <FormField label="排序值" help="数字越小越靠前">
          <input className={styles.input} type="number" value={sortOrder} onChange={(e) => setSortOrder(Number(e.target.value))} style={{ width: 120 }} />
        </FormField>
      </div>
      <FormField label="门店图">
        <Upload value={imageUrl} onChange={setImageUrl} dir="stores" />
      </FormField>
      <FormField label="启用状态">
        <div className={styles.switchRow}>
          <Switch checked={isActive} onChange={setIsActive} label="启用状态" />
          <span className={styles.switchText}>{isActive ? '启用（前台展示）' : '停用（前台隐藏）'}</span>
        </div>
      </FormField>
    </Modal>
  )
}
