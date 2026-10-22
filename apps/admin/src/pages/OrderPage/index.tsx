// ============================================================
// 文件功能：订单管理（UI-UX §6.4，PRD F11）
// 功能：列表筛选/搜索、状态流转（后端状态机 40001 拦截）、
//       新增/编辑弹窗（产品下拉→规格联动、金额只读）、详情查看
// ============================================================

import { useCallback, useEffect, useState } from 'react'
import { client } from '@/api/client'
import type { CakeRow, OrderDetail, OrderPayload, OrderRow, OrderStatus, PageResult } from '@/api/types'
import {
  PageHeader, Table, Modal, StatusBadge, Tag, Pagination, Toast, Spinner,
} from '@/components/AdminComponents'
import { Button, FormField, SearchInput, Select } from '@/components/AdminForm'
import { formatDateTime } from '@/utils/datetime'
import styles from './OrderPage.module.css'

const STATUS_FILTERS: { key: OrderStatus | 'all'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待处理' },
  { key: 'confirmed', label: '已确认' },
  { key: 'completed', label: '已完成' },
  { key: 'cancelled', label: '已取消' },
]

export default function OrderPage() {
  const [orders, setOrders] = useState<OrderRow[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(12)
  const [statusFilter, setStatusFilter] = useState<OrderStatus | 'all'>('all')
  const [keyword, setKeyword] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  // 弹窗状态
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<OrderDetail | null>(null)
  const [viewing, setViewing] = useState<OrderDetail | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  function showToast(type: 'success' | 'error', text: string) {
    setToast({ type, text })
    setTimeout(() => setToast(null), 4000)
  }

  // ---------- 加载列表 ----------
  const loadList = useCallback(() => {
    setLoading(true)
    client.get('/orders', {
      params: { keyword: search || undefined, status: statusFilter === 'all' ? undefined : statusFilter, page, page_size: pageSize },
    })
      .then((r) => {
        const d = r.data.data as PageResult<OrderRow>
        setOrders(d.items); setTotal(d.total); setTotalPages(d.total_pages)
      })
      .catch(() => { setOrders([]); setTotal(0) })
      .finally(() => setLoading(false))
  }, [search, statusFilter, page, pageSize])

  useEffect(() => { loadList() }, [loadList])

  function changeStatusFilter(s: string) { setStatusFilter(s as OrderStatus | 'all'); setPage(1) }
  function doSearch() { setSearch(keyword); setPage(1) }

  // ---------- 状态流转 ----------
  async function changeStatus(order: OrderRow, status: OrderStatus) {
    try {
      await client.patch(`/orders/${order.id}/status`, { status })
      showToast('success', `订单已${STATUS_FILTERS.find((s) => s.key === status)?.label}`)
      loadList()
    } catch (e) {
      // 非法流转 → 后端 40001 拦截提示
      showToast('error', (e as Error).message)
    }
  }

  // ---------- 查看详情 ----------
  function openView(order: OrderRow) {
    client.get(`/orders/${order.id}`).then((r) => setViewing(r.data.data as OrderDetail)).catch((e) => showToast('error', (e as Error).message))
  }
  function openEdit(order: OrderRow) {
    client.get(`/orders/${order.id}`).then((r) => { setEditing(r.data.data as OrderDetail); setModalOpen(true) }).catch((e) => showToast('error', (e as Error).message))
  }

  return (
    <div>
      <PageHeader meta="ORDERS · 订单管理" title="订单管理"
        actions={<Button onClick={() => { setEditing(null); setModalOpen(true) }}>＋ 新增订单</Button>} />

      {/* ---------- 工具栏 ---------- */}
      <div className={styles.toolbar}>
        <div className={styles.filters}>
          {STATUS_FILTERS.map((s) => (
            <Tag key={s.key} active={statusFilter === s.key} onClick={() => changeStatusFilter(s.key)}>{s.label}</Tag>
          ))}
        </div>
        <div className={styles.toolRight}>
          <SearchInput value={keyword} onChange={setKeyword} onSearch={doSearch} placeholder="搜索客户姓名 / 订单号" />
          <Select
            value={statusFilter === 'all' ? '' : statusFilter}
            onChange={changeStatusFilter}
            placeholder="全部状态"
            ariaLabel="按状态筛选"
            options={STATUS_FILTERS.filter((s) => s.key !== 'all').map((s) => ({ value: s.key, label: s.label }))}
          />
        </div>
      </div>

      {/* ---------- 表格 ---------- */}
      {loading ? <Spinner text="订单加载中…" /> : (
        <Table
          rowKey="id"
          data={orders as unknown as Record<string, unknown>[]}
          columns={[
            { key: 'order_no', title: '订单号', render: (r) => <span className={styles.orderNo}>{String(r.order_no)}</span> },
            { key: 'customer_name', title: '客户', render: (r) => String(r.customer_name) },
            { key: 'customer_phone', title: '联系电话', render: (r) => <span className={styles.phone}>{String(r.customer_phone)}</span> },
            { key: 'product', title: '订购产品', render: (r) => <>{String(r.cake_name)}<span className={styles.spec}>·{String(r.spec_name)}</span></> },
            { key: 'quantity', title: '数量', render: (r) => `×${String(r.quantity)}` },
            { key: 'amount', title: '金额', render: (r) => <span className={styles.amount}>¥{String(r.amount)}</span> },
            { key: 'pickup_type', title: '取货', render: (r) => String(r.pickup_type) === 'self' ? '自提' : '配送' },
            { key: 'status', title: '状态', render: (r) => <StatusBadge status={String(r.status)} /> },
            { key: 'created_at', title: '下单时间', render: (r) => <span className={styles.time}>{formatDateTime(String(r.created_at))}</span> },
            { key: 'ops', title: '操作', render: (r) => {
                const o = r as unknown as OrderRow
                return (
                  <div className={styles.ops}>
                    <Button variant="text" size="sm" onClick={() => openView(o)}>查看</Button>
                    {o.status !== 'completed' && o.status !== 'cancelled' && (
                      <Button variant="text" size="sm" onClick={() => openEdit(o)}>编辑</Button>
                    )}
                    {o.status === 'pending' && (
                      <Button variant="text" size="sm" onClick={() => changeStatus(o, 'confirmed')}>确认</Button>
                    )}
                    {o.status === 'confirmed' && (
                      <Button variant="text" size="sm" onClick={() => changeStatus(o, 'completed')}>完成</Button>
                    )}
                    {(o.status === 'pending' || o.status === 'confirmed') && (
                      <Button variant="text" size="sm" onClick={() => changeStatus(o, 'cancelled')}>取消</Button>
                    )}
                  </div>
                )
              } },
          ]}
        />
      )}

      <Pagination page={page} totalPages={totalPages} onChange={setPage} />

      {/* ---------- 状态机示意条 ---------- */}
      <div className={styles.machineBar}>
        <span className={styles.machineLabel}>状态流转</span>
        <div className={styles.machineFlow}>
          <span className={styles.machineStep}>待处理</span>
          <span className={styles.machineArrow}>→</span>
          <span className={styles.machineStep}>已确认</span>
          <span className={styles.machineArrow}>→</span>
          <span className={styles.machineStep}>已完成</span>
          <span className={styles.machineDivider}>｜</span>
          <span className={styles.machineStep}>任意阶段可取消</span>
          <span className={styles.machineArrow}>→</span>
          <span className={styles.machineStep}>已取消</span>
        </div>
        <span className={styles.machineNote}>已完成 / 已取消不可再变更</span>
      </div>

      {/* ---------- 新增/编辑订单弹窗 ---------- */}
      <OrderModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        editing={editing}
        onSaved={() => { setModalOpen(false); loadList() }}
        onToast={(t) => showToast(t.type, t.text)}
      />

      {/* ---------- 详情弹窗 ---------- */}
      <Modal open={!!viewing} title="订单详情" onClose={() => setViewing(null)}>
        {viewing && (
          <div className={styles.detailGrid}>
            <DetailRow label="订单号" value={viewing.order_no} />
            <DetailRow label="客户姓名" value={viewing.customer_name} />
            <DetailRow label="联系电话" value={viewing.customer_phone} />
            <DetailRow label="订购产品" value={`${viewing.cake_snapshot.cake_name} · ${viewing.cake_snapshot.spec_name}`} />
            <DetailRow label="数量" value={`×${viewing.quantity}`} />
            <DetailRow label="订单金额" value={`¥${viewing.amount}`} bold />
            <DetailRow label="取货方式" value={viewing.pickup_type === 'self' ? '到店自提' : '配送'} />
            {viewing.delivery_address && <DetailRow label="配送地址" value={viewing.delivery_address} />}
            {viewing.custom_note && <DetailRow label="定制需求" value={viewing.custom_note} />}
            {viewing.remark && <DetailRow label="备注" value={viewing.remark} />}
            <DetailRow label="订单状态" value={<StatusBadge status={viewing.status} />} />
            <DetailRow label="下单时间" value={formatDateTime(viewing.created_at)} />
          </div>
        )}
      </Modal>

      <Toast toast={toast} />
    </div>
  )
}

function DetailRow({ label, value, bold }: { label: string; value: React.ReactNode; bold?: boolean }) {
  return (
    <div className={styles.detailRow}>
      <span className={styles.detailLabel}>{label}</span>
      <span className={`${styles.detailValue} ${bold ? styles.detailValueBold : ''}`}>{value}</span>
    </div>
  )
}

// ============================================================
// 新增/编辑订单弹窗（产品下拉 → 规格联动 → 金额只读展示）
// ============================================================
function OrderModal({ open, onClose, editing, onSaved, onToast }: {
  open: boolean
  onClose: () => void
  editing: OrderDetail | null
  onSaved: () => void
  onToast: (t: { type: 'success' | 'error'; text: string }) => void
}) {
  const [customerName, setCustomerName] = useState('')
  const [customerPhone, setCustomerPhone] = useState('')
  const [cakeId, setCakeId] = useState('')
  const [specName, setSpecName] = useState('')
  const [quantity, setQuantity] = useState(1)
  const [pickupType, setPickupType] = useState<'self' | 'delivery'>('self')
  const [deliveryAddress, setDeliveryAddress] = useState('')
  const [customNote, setCustomNote] = useState('')
  const [remark, setRemark] = useState('')
  const [cakes, setCakes] = useState<CakeRow[]>([])
  const [specList, setSpecList] = useState<{ name: string; price: number }[]>([])
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  // 拉取某个产品的规格列表（列表接口不含 specs，需详情接口）
  function loadSpecs(id: string) {
    if (!id) { setSpecList([]); return }
    client.get(`/cakes/${id}`)
      .then((r) => {
        const specs = (r.data.data as { specs: { name: string; price: number }[] }).specs ?? []
        setSpecList(specs)
      })
      .catch(() => setSpecList([]))
  }

  // 打开时：加载上架产品下拉（仅上架）+ 回填编辑数据
  useEffect(() => {
    if (!open) return
    setErrors({})
    // page_size 上限 50（后端约束，admin/cakes 协议），超过会被 40001 拒掉导致 setCakes([]) 清空
    client.get('/cakes', { params: { is_active: 1, page_size: 50 } })
      .then((r) => setCakes(r.data.data.items as CakeRow[]))
      .catch(() => setCakes([]))

    if (editing) {
      setCustomerName(editing.customer_name)
      setCustomerPhone(editing.customer_phone)
      setCakeId(String(editing.cake_snapshot.cake_id))
      setSpecName(editing.cake_snapshot.spec_name)
      setQuantity(editing.quantity)
      setPickupType(editing.pickup_type)
      setDeliveryAddress(editing.delivery_address ?? '')
      setCustomNote(editing.custom_note ?? '')
      setRemark(editing.remark ?? '')
      // 回填时拉取该产品的完整规格列表
      loadSpecs(String(editing.cake_snapshot.cake_id))
    } else {
      setCustomerName(''); setCustomerPhone(''); setCakeId(''); setSpecName('')
      setQuantity(1); setPickupType('self'); setDeliveryAddress(''); setCustomNote(''); setRemark('')
      setSpecList([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editing])

  // 金额实时计算（只读展示，后端为准）
  const currentSpec = specList.find((s) => s.name === specName)
  const previewAmount = currentSpec ? currentSpec.price * quantity : 0

  // 选择产品 → 拉规格 + 默认选中第一个
  function onCakeChange(v: string) {
    setCakeId(v)
    setSpecName('')
    loadSpecs(v)
    setErrors((p) => ({ ...p, cake: '', spec: '' }))
  }

  function validate(): boolean {
    const next: Record<string, string> = {}
    if (customerName.trim().length < 2 || customerName.trim().length > 20) next.customerName = '姓名需为 2-20 个字符'
    if (!/^1[3-9]\d{9}$/.test(customerPhone.trim())) next.customerPhone = '请输入 11 位有效手机号'
    if (!cakeId) next.cake = '请选择订购产品'
    if (!specName) next.spec = '请选择规格'
    if (!(Number(quantity) >= 1)) next.quantity = '数量至少为 1'
    if (pickupType === 'delivery' && !deliveryAddress.trim()) next.address = '配送订单必须填写配送地址'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function submit() {
    if (!validate() || saving) return
    setSaving(true)
    const payload: OrderPayload = {
      customer_name: customerName.trim(),
      customer_phone: customerPhone.trim(),
      cake_id: Number(cakeId),
      spec_name: specName,
      quantity: Number(quantity),
      pickup_type: pickupType,
      delivery_address: pickupType === 'delivery' ? deliveryAddress.trim() : undefined,
      custom_note: customNote.trim() || undefined,
      remark: remark.trim() || undefined,
    }
    try {
      if (editing) {
        await client.put(`/orders/${editing.id}`, payload)
        onToast({ type: 'success', text: '订单已更新' })
      } else {
        await client.post('/orders', payload)
        onToast({ type: 'success', text: '订单已新增' })
      }
      onSaved()
    } catch (e) {
      onToast({ type: 'error', text: (e as Error).message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} title={editing ? '编辑订单' : '新增订单'} onClose={onClose} width={680}
      footer={<>
        <Button variant="ghost" onClick={onClose}>取消</Button>
        <Button onClick={submit} disabled={saving}>{saving ? '保存中…' : '保存'}</Button>
      </>}>
      <div className={styles.formRow2}>
        <FormField label="客户姓名" required error={errors.customerName}>
          <input className={`${styles.input} ${errors.customerName ? styles.inputError : ''}`} value={customerName}
            maxLength={20} placeholder="如：林小姐"
            onChange={(e) => { setCustomerName(e.target.value); if (errors.customerName) setErrors((p) => ({ ...p, customerName: '' })) }} />
        </FormField>
        <FormField label="联系电话" required error={errors.customerPhone}>
          <input className={`${styles.input} ${errors.customerPhone ? styles.inputError : ''}`} value={customerPhone}
            maxLength={11} placeholder="11 位手机号"
            onChange={(e) => { setCustomerPhone(e.target.value); if (errors.customerPhone) setErrors((p) => ({ ...p, customerPhone: '' })) }} />
        </FormField>
      </div>

      <div className={styles.formRow2}>
        <FormField label="订购产品" required error={errors.cake}>
          <select className={`${styles.input} ${errors.cake ? styles.inputError : ''}`} value={cakeId}
            onChange={(e) => onCakeChange(e.target.value)}>
            <option value="">请选择产品（仅上架）</option>
            {cakes.map((c) => <option key={c.id} value={c.id}>{c.name}（¥{c.price_from} 起）</option>)}
          </select>
        </FormField>
        <FormField label="规格" required error={errors.spec}>
          <select className={`${styles.input} ${errors.spec ? styles.inputError : ''}`} value={specName}
            onChange={(e) => { setSpecName(e.target.value); if (errors.spec) setErrors((p) => ({ ...p, spec: '' })) }}
            disabled={!cakeId}>
            <option value="">{cakeId ? '请选择规格' : '请先选择产品'}</option>
            {specList.map((s) => <option key={s.name} value={s.name}>{s.name}（¥{s.price}）</option>)}
          </select>
        </FormField>
      </div>

      <div className={styles.formRow2}>
        <FormField label="数量" required error={errors.quantity}>
          <input className={`${styles.input} ${errors.quantity ? styles.inputError : ''}`} type="number" min="1"
            value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} style={{ width: 120 }} />
        </FormField>
        <FormField label="取货方式" required>
          <div className={styles.pickupRow}>
            {(['self', 'delivery'] as const).map((p) => (
              <button key={p} type="button"
                className={`${styles.pickupBtn} ${pickupType === p ? styles.pickupActive : ''}`}
                onClick={() => setPickupType(p)}>
                {p === 'self' ? '到店自提' : '配送'}
              </button>
            ))}
          </div>
        </FormField>
      </div>

      {pickupType === 'delivery' && (
        <FormField label="配送地址" required error={errors.address}>
          <input className={`${styles.input} ${errors.address ? styles.inputError : ''}`} value={deliveryAddress}
            maxLength={100} placeholder="详细配送地址"
            onChange={(e) => { setDeliveryAddress(e.target.value); if (errors.address) setErrors((p) => ({ ...p, address: '' })) }} />
        </FormField>
      )}

      <FormField label="定制需求" help={`${customNote.length}/500`}>
        <textarea className={styles.input} rows={2} value={customNote} maxLength={500}
          onChange={(e) => setCustomNote(e.target.value)} placeholder="选填：定制口味/图案/祝福语" />
      </FormField>

      <FormField label="备注" help={`${remark.length}/500`}>
        <textarea className={styles.input} rows={2} value={remark} maxLength={500}
          onChange={(e) => setRemark(e.target.value)} placeholder="选填：内部备注" />
      </FormField>

      {/* 金额区（只读展示，后端为准） */}
      <div className={styles.amountBox}>
        <span className={styles.amountLabel}>订单金额自动计算 = 规格价格 × 数量（不可手改）</span>
        <span className={styles.amountValue}>¥{previewAmount.toFixed(2).replace(/\.00$/, '')}</span>
      </div>
    </Modal>
  )
}
