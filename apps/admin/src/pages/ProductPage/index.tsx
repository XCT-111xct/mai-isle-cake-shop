// ============================================================
// 文件功能：商品管理（UI-UX §6.3，PRD F10）
// 功能：列表筛选/搜索、新增编辑弹窗（规格子表/图片上传/开关）、
//       上下架（不支持删除）、分类管理（Tag + 迁移删除）
// ============================================================

import { useCallback, useEffect, useState } from 'react'
import { client } from '@/api/client'
import type { CakeRow, CakeDetail, CategoryRow, PageResult } from '@/api/types'
import {
  PageHeader, Table, Modal, Switch, StatusBadge, Tag, Empty,
  Pagination, Toast, Spinner,
} from '@/components/AdminComponents'
import { Button, FormField, SearchInput, Select, Upload } from '@/components/AdminForm'
import styles from './ProductPage.module.css'

// ---------- 筛选 tag 定义 ----------
type FilterKey = 'all' | 'active' | 'inactive' | 'featured'
const FILTERS: { key: FilterKey; label: string; match: (c: CakeRow) => boolean }[] = [
  { key: 'all', label: '全部', match: () => true },
  { key: 'active', label: '上架', match: (c) => c.is_active },
  { key: 'inactive', label: '下架', match: (c) => !c.is_active },
  { key: 'featured', label: '首页推荐', match: (c) => c.is_featured },
]

export default function ProductPage() {
  // ---------- 列表状态 ----------
  const [cakes, setCakes] = useState<CakeRow[]>([])
  const [categories, setCategories] = useState<CategoryRow[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(12)
  const [filter, setFilter] = useState<FilterKey>('all')
  const [keyword, setKeyword] = useState('')
  const [search, setSearch] = useState('')
  const [categoryId, setCategoryId] = useState<number | undefined>()
  const [loading, setLoading] = useState(true)

  // ---------- 弹窗状态 ----------
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<CakeDetail | null>(null)

  // ---------- 分类管理状态 ----------
  const [cateModal, setCateModal] = useState(false)             // 新增分类弹窗
  const [newCateName, setNewCateName] = useState('')
  const [moveModal, setMoveModal] = useState<{ catId: number; catName: string } | null>(null) // 迁移弹窗
  const [moveTarget, setMoveTarget] = useState('')

  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  function showToast(type: 'success' | 'error', text: string) {
    setToast({ type, text })
    setTimeout(() => setToast(null), 4000)
  }

  // ---------- 数据加载（列表 + 分类） ----------
  const loadList = useCallback(() => {
    setLoading(true)
    client.get('/cakes', { params: { keyword: search || undefined, category_id: categoryId, page, page_size: pageSize } })
      .then((r) => {
        const d = r.data.data as PageResult<CakeRow>
        setCakes(d.items)
        setTotal(d.total)
        setTotalPages(d.total_pages)
      })
      .catch(() => { setCakes([]); setTotal(0) })
      .finally(() => setLoading(false))
  }, [search, categoryId, page, pageSize])

  const loadCategories = useCallback(() => {
    client.get('/categories')
      .then((r) => setCategories(r.data.data.items as CategoryRow[]))
      .catch(() => setCategories([]))
  }, [])

  useEffect(() => { loadList() }, [loadList])
  useEffect(() => { loadCategories() }, [loadCategories])

  // ---------- 筛选/搜索/分页（重置 page=1 用 loadList 的依赖触发） ----------
  function changeFilter(f: FilterKey) { setFilter(f); setPage(1) }
  function doSearch() { setSearch(keyword); setPage(1) }
  function changeCategory(cid: string) { setCategoryId(cid ? Number(cid) : undefined); setPage(1) }

  // 当前筛选下的数据（前端过滤：tag 是展示态，数据仍来自后端分页）
  const filteredCakes = cakes.filter(FILTERS.find((f) => f.key === filter)!.match)

  // ---------- 上下架 ----------
  async function toggleActive(cake: CakeRow) {
    try {
      await client.patch(`/cakes/${cake.id}/status`, { is_active: !cake.is_active })
      showToast('success', cake.is_active ? `「${cake.name}」已下架` : `「${cake.name}」已上架`)
      loadList()
    } catch (e) {
      showToast('error', (e as Error).message)
    }
  }

  // ---------- 打开新增/编辑弹窗 ----------
  function openCreate() { setEditing(null); setModalOpen(true) }
  function openEdit(cake: CakeRow) {
    client.get(`/cakes/${cake.id}`).then((r) => {
      setEditing(r.data.data as CakeDetail)
      setModalOpen(true)
    }).catch((e) => showToast('error', (e as Error).message))
  }

  // ---------- 新增分类 ----------
  async function addCategory() {
    if (!newCateName.trim()) return
    try {
      await client.post('/categories', { name: newCateName.trim(), sort_order: categories.length + 1 })
      setCateModal(false)
      setNewCateName('')
      showToast('success', '分类已新增')
      loadCategories()
    } catch (e) {
      showToast('error', (e as Error).message)
    }
  }

  // ---------- 删除分类（有产品 → 迁移弹窗） ----------
  async function removeCategory(cat: CategoryRow) {
    if (cat.cake_count > 0) {
      // 该分类下有产品：先迁移
      setMoveModal({ catId: cat.id, catName: cat.name })
      setMoveTarget('')
      return
    }
    if (!window.confirm(`确认删除分类「${cat.name}」？`)) return
    try {
      await client.delete(`/categories/${cat.id}`)
      showToast('success', '分类已删除')
      loadCategories()
    } catch (e) {
      showToast('error', (e as Error).message)
    }
  }

  // ---------- 迁移后删除 ----------
  async function confirmMove() {
    if (!moveModal || !moveTarget) return
    try {
      await client.delete(`/categories/${moveModal.catId}`, { params: { move_to_id: moveTarget } })
      setMoveModal(null)
      showToast('success', '产品已迁移，分类已删除')
      loadCategories()
      loadList()
    } catch (e) {
      showToast('error', (e as Error).message)
    }
  }

  return (
    <div>
      <PageHeader
        meta="PRODUCTS · 商品管理"
        title="商品管理"
        actions={<Button onClick={openCreate}>＋ 新增蛋糕</Button>}
      />

      {/* ---------- 工具栏：筛选 tag + 搜索 + 分类下拉 ---------- */}
      <div className={styles.toolbar}>
        <div className={styles.filters}>
          {FILTERS.map((f) => (
            <Tag key={f.key} active={filter === f.key} onClick={() => changeFilter(f.key)}>
              {f.label}
              <span className={styles.tagNum}>{f.key === 'all' ? total : cakes.filter(f.match).length}</span>
            </Tag>
          ))}
        </div>
        <div className={styles.toolRight}>
          <SearchInput value={keyword} onChange={setKeyword} onSearch={doSearch} placeholder="搜索产品名称" />
          <Select
            value={categoryId}
            onChange={changeCategory}
            placeholder="全部分类"
            ariaLabel="按分类筛选"
            options={categories.map((c) => ({ value: c.id, label: c.name }))}
          />
        </div>
      </div>

      {/* ---------- 表格 ---------- */}
      {loading ? <Spinner text="商品加载中…" /> : (
        <Table
          rowKey="id"
          data={filteredCakes as unknown as Record<string, unknown>[]}
          columns={[
            { key: 'id', title: 'ID', width: '60px', render: (r) => `#${r.id}` },
            { key: 'image_url', title: '产品图', render: (r) => (
                <img className={styles.thumb} src={r.image_url as string || '/placeholder-cake.svg'} alt={String(r.name)} />
              ) },
            { key: 'name', title: '名称', render: (r) => <span className={styles.nameCell}>{String(r.name)}</span> },
            { key: 'category', title: '分类', render: (r) => String(r.category) },
            { key: 'spec_count', title: '规格数', render: (r) => `${String(r.spec_count)} 种` },
            { key: 'price_from', title: '起价', render: (r) => <span className={styles.amount}>¥{String(r.price_from)}</span> },
            { key: 'sort_order', title: '排序', render: (r) => String(r.sort_order) },
            { key: 'is_featured', title: '推荐', render: (r) => r.is_featured ? <span className={styles.star} title="首页推荐">★</span> : <span className={styles.starOff}>☆</span> },
            { key: 'is_active', title: '状态', render: (r) => <StatusBadge status={r.is_active ? 'active' : 'inactive'} /> },
            { key: 'ops', title: '操作', render: (r) => {
                const cake = r as unknown as CakeRow
                return (
                  <div className={styles.ops}>
                    <Button variant="text" size="sm" onClick={() => openEdit(cake)}>编辑</Button>
                    {/* 下架按钮 hover 提示"产品不支持删除"（防误触） */}
                    <Button variant="text" size="sm" onClick={() => toggleActive(cake)}>
                      {cake.is_active ? '下架' : '上架'}
                    </Button>
                  </div>
                )
              } },
          ]}
        />
      )}

      <Pagination page={page} totalPages={totalPages} onChange={setPage} />

      {/* ---------- 分类管理区 ---------- */}
      <div className={styles.cateSection}>
        <div className={styles.cateHead}>
          <h3 className={styles.cateTitle}>分类管理</h3>
          <span className={styles.cateHint}>删除有产品的分类时需先迁移产品到其他分类</span>
        </div>
        <div className={styles.cateTags}>
          {categories.map((c) => (
            <Tag key={c.id} onRemove={() => removeCategory(c)}>
              {c.name}
              <span className={styles.tagNum}>{c.cake_count}</span>
            </Tag>
          ))}
          <button type="button" className={styles.addCate} onClick={() => setCateModal(true)}>＋ 新增分类</button>
        </div>
      </div>

      {/* ---------- 新增/编辑弹窗 ---------- */}
      <CakeModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        editing={editing}
        categories={categories}
        onSaved={() => { setModalOpen(false); loadList(); loadCategories(); }}
        onToast={(t) => showToast(t.type, t.text)}
      />

      {/* ---------- 新增分类弹窗 ---------- */}
      <Modal open={cateModal} title="新增分类" onClose={() => setCateModal(false)}
        footer={<>
          <Button variant="ghost" onClick={() => setCateModal(false)}>取消</Button>
          <Button onClick={addCategory} disabled={!newCateName.trim()}>保存</Button>
        </>}>
        <FormField label="分类名称" required>
          <input className={styles.input} value={newCateName} maxLength={20}
            onChange={(e) => setNewCateName(e.target.value)} placeholder="请输入分类名称（如：红丝绒系列）" />
        </FormField>
      </Modal>

      {/* ---------- 迁移删除确认弹窗 ---------- */}
      <Modal open={!!moveModal} title="迁移产品" onClose={() => setMoveModal(null)}
        footer={<>
          <Button variant="ghost" onClick={() => setMoveModal(null)}>取消</Button>
          <Button onClick={confirmMove} disabled={!moveTarget}>迁移并删除</Button>
        </>}>
        <p className={styles.moveDesc}>
          分类「<b>{moveModal?.catName}</b>」下有 {categories.find((c) => c.id === moveModal?.catId)?.cake_count ?? 0} 个产品，
          请选择迁移目标分类后删除：
        </p>
        <FormField label="目标分类" required>
          <select className={styles.input} value={moveTarget} onChange={(e) => setMoveTarget(e.target.value)}>
            <option value="">请选择…</option>
            {categories.filter((c) => c.id !== moveModal?.catId).map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </FormField>
      </Modal>

      <Toast toast={toast} />
    </div>
  )
}

// ============================================================
// 新增/编辑商品弹窗（规格子表 + 上传 + 开关）
// ============================================================
function CakeModal({ open, onClose, editing, categories, onSaved, onToast }: {
  open: boolean
  onClose: () => void
  editing: CakeDetail | null
  categories: CategoryRow[]
  onSaved: () => void
  onToast: (t: { type: 'success' | 'error'; text: string }) => void
}) {
  // 表单状态
  const [name, setName] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [specs, setSpecs] = useState<{ name: string; price: string }[]>([{ name: '', price: '' }])
  const [imageUrl, setImageUrl] = useState('')
  const [description, setDescription] = useState('')
  const [isFeatured, setIsFeatured] = useState(false)
  const [isActive, setIsActive] = useState(true)
  const [sortOrder, setSortOrder] = useState(1)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [uploading, setUploading] = useState(false)

  // 打开时回填（编辑）或初始化（新增）
  useEffect(() => {
    if (!open) return
    if (editing) {
      setName(editing.name)
      setCategoryId(String(editing.category_id))
      setSpecs(editing.specs.map((s) => ({ name: s.name, price: String(s.price) })))
      setImageUrl(editing.image_url)
      setDescription(editing.description ?? '')
      setIsFeatured(editing.is_featured)
      setIsActive(editing.is_active)
      setSortOrder(editing.sort_order)
    } else {
      setName(''); setCategoryId(categories[0] ? String(categories[0].id) : '')
      setSpecs([{ name: '', price: '' }]); setImageUrl(''); setDescription('')
      setIsFeatured(false); setIsActive(true); setSortOrder(1)
    }
    setErrors({})
  }, [open, editing, categories])

  // ---------- 规格子表操作 ----------
  function addSpec() { setSpecs((s) => [...s, { name: '', price: '' }]) }
  function removeSpec(i: number) { setSpecs((s) => s.filter((_, idx) => idx !== i)) }
  function updateSpec(i: number, field: 'name' | 'price', v: string) {
    setSpecs((s) => s.map((row, idx) => (idx === i ? { ...row, [field]: v } : row)))
  }

  // ---------- 校验（错误 state 派生，整体覆盖） ----------
  function validate(): boolean {
    const next: Record<string, string> = {}
    if (name.trim().length < 2 || name.trim().length > 50) next.name = '名称需为 2-50 个字符'
    if (!categoryId) next.category = '请选择分类'
    if (specs.length === 0 || specs.some((s) => !s.name.trim())) next.specs = '规格名称不能为空'
    if (specs.some((s) => !(Number(s.price) > 0))) next.specs = '规格价格需大于 0'
    if (!imageUrl) next.image = '请上传产品图'
    if (description.length > 2000) next.description = '描述不能超过 2000 字'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  // ---------- 保存 ----------
  async function submit() {
    if (!validate() || saving) return
    setSaving(true)
    const payload = {
      name: name.trim(),
      category_id: Number(categoryId),
      specs: specs.map((s) => ({ name: s.name.trim(), price: Number(Number(s.price).toFixed(2)) })),
      image_url: imageUrl,
      description: description.trim() || undefined,
      is_featured: isFeatured,
      is_active: isActive,
      sort_order: Number(sortOrder) || 1,
    }
    try {
      if (editing) {
        await client.put(`/cakes/${editing.id}`, payload)
        onToast({ type: 'success', text: '商品已更新' })
      } else {
        await client.post('/cakes', payload)
        onToast({ type: 'success', text: '商品已新增' })
      }
      onSaved()
    } catch (e) {
      // 重名 40900："产品名称已存在，请更换"
      onToast({ type: 'error', text: (e as Error).message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} title={editing ? '编辑蛋糕' : '新增蛋糕'} onClose={onClose} width={680}
      footer={<>
        <Button variant="ghost" onClick={onClose}>取消</Button>
        <Button onClick={submit} disabled={saving || uploading}>{saving ? '保存中…' : '保存'}</Button>
      </>}>
      <div className={styles.formRow2}>
        <FormField label="产品名称" required error={errors.name}>
          <input className={`${styles.input} ${errors.name ? styles.inputError : ''}`}
            value={name} maxLength={50}
            onChange={(e) => { setName(e.target.value); if (errors.name) setErrors((p) => ({ ...p, name: '' })) }}
            placeholder="2-50 字，且不能与其他产品重名" />
        </FormField>
        <FormField label="所属分类" required error={errors.category}>
          <select className={`${styles.input} ${errors.category ? styles.inputError : ''}`}
            value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">请选择分类</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </FormField>
      </div>

      {/* 规格配置子表 */}
      <FormField label="规格配置" required error={errors.specs}
        help="至少保留 1 个规格；价格单位为元，最多两位小数">
        <div className={styles.specTable}>
          <div className={styles.specHeadRow}>
            <span>规格名</span><span>价格（元）</span><span></span>
          </div>
          {specs.map((s, i) => (
            <div key={i} className={styles.specRow}>
              <input className={styles.input} value={s.name} placeholder="如：6 寸"
                onChange={(e) => updateSpec(i, 'name', e.target.value)} />
              <input className={styles.input} type="number" min="0" step="0.01" value={s.price} placeholder="如：168"
                onChange={(e) => updateSpec(i, 'price', e.target.value)} />
              <button type="button" className={styles.specDel} onClick={() => removeSpec(i)}
                disabled={specs.length <= 1} aria-label="删除该规格">×</button>
            </div>
          ))}
          <button type="button" className={styles.addSpec} onClick={addSpec}>＋ 添加规格</button>
        </div>
      </FormField>

      <FormField label="产品图" required error={errors.image}>
        <Upload value={imageUrl} onChange={setImageUrl} onUploading={setUploading} dir="cakes" />
      </FormField>

      <FormField label="产品描述" error={errors.description} help={`${description.length}/2000`}>
        <textarea className={`${styles.input} ${styles.textarea} ${errors.description ? styles.inputError : ''}`}
          value={description} rows={3} maxLength={2000}
          onChange={(e) => { setDescription(e.target.value); if (errors.description) setErrors((p) => ({ ...p, description: '' })) }}
          placeholder="选填：产品介绍、卖点（≤2000 字）" />
      </FormField>

      <div className={styles.formRow2}>
        <FormField label="首页推荐">
          <div className={styles.switchRow}>
            <Switch checked={isFeatured} onChange={setIsFeatured} label="首页推荐" />
            <span className={styles.switchText}>{isFeatured ? '推荐' : '不推荐'}</span>
          </div>
        </FormField>
        <FormField label="上架状态">
          <div className={styles.switchRow}>
            <Switch checked={isActive} onChange={setIsActive} label="上架状态" />
            <span className={styles.switchText}>{isActive ? '上架中' : '已下架'}</span>
          </div>
        </FormField>
      </div>

      <FormField label="排序值" help="数字越小越靠前（列表与首页推荐共用）">
        <input className={styles.input} type="number" value={sortOrder}
          onChange={(e) => setSortOrder(Number(e.target.value))} style={{ width: 120 }} />
      </FormField>
    </Modal>
  )
}
