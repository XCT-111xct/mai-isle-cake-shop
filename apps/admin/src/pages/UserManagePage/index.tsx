// ============================================================
// 文件功能：管理员管理（UI-UX §6.8，PRD F15，仅超管可见）
// 功能：列表 / 新增 / 编辑 / 重置密码 / 停用启用
// 规则：
//   1. 账号唯一；密码由超管重置
//   2. 超管账号不可删除、无停用按钮
//   3. 系统至少保留 1 个超管（后端拦截 + 前端提示）
// ============================================================

import { useCallback, useEffect, useState } from 'react'
import { client } from '@/api/client'
import type { UserManageRow, PageResult, UserPayload } from '@/api/types'
import {
  PageHeader, Table, Modal, StatusBadge, RoleBadge, Tag, Pagination, Toast, Spinner, Switch,
} from '@/components/AdminComponents'
import { Button, FormField } from '@/components/AdminForm'
import styles from './UserManagePage.module.css'

export default function UserManagePage() {
  const [users, setUsers] = useState<UserManageRow[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(12)
  const [roleFilter, setRoleFilter] = useState<'all' | 'super' | 'ops'>('all')
  const [loading, setLoading] = useState(true)

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<UserManageRow | null>(null)
  const [resetModal, setResetModal] = useState<UserManageRow | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  function showToast(type: 'success' | 'error', text: string) {
    setToast({ type, text })
    setTimeout(() => setToast(null), 4000)
  }

  const loadList = useCallback(() => {
    setLoading(true)
    client.get('/users', { params: { role: roleFilter === 'all' ? undefined : roleFilter, page, page_size: pageSize } })
      .then((r) => {
        const d = r.data.data as PageResult<UserManageRow>
        setUsers(d.items); setTotal(d.total); setTotalPages(d.total_pages)
      })
      .catch(() => setUsers([]))
      .finally(() => setLoading(false))
  }, [roleFilter, page, pageSize])

  useEffect(() => { loadList() }, [loadList])

  function changeRoleFilter(s: string) { setRoleFilter(s as 'all' | 'super' | 'ops'); setPage(1) }

  // 停用 / 启用
  async function toggleActive(u: UserManageRow) {
    try {
      await client.patch(`/users/${u.id}/status`, { is_active: !u.is_active })
      showToast('success', u.is_active ? `已停用「${u.name}」（无法登录）` : `已启用「${u.name}」`)
      loadList()
    } catch (e) { showToast('error', (e as Error).message) }
  }

  // 重置密码
  async function doReset(newPassword: string) {
    if (!resetModal) return
    try {
      await client.patch(`/users/${resetModal.id}/password`, { new_password: newPassword })
      setResetModal(null)
      showToast('success', `「${resetModal.name}」密码已重置`)
    } catch (e) { showToast('error', (e as Error).message) }
  }

  function openCreate() { setEditing(null); setModalOpen(true) }
  function openEdit(u: UserManageRow) { setEditing(u); setModalOpen(true) }

  return (
    <div>
      <PageHeader meta="USERS · 管理员管理" title="管理员管理"
        actions={<Button onClick={openCreate}>＋ 新增管理员</Button>} />

      {/* 工具栏：角色 tag */}
      <div className={styles.toolbar}>
        <div className={styles.filters}>
          <Tag active={roleFilter === 'all'} onClick={() => changeRoleFilter('all')}>全部</Tag>
          <Tag active={roleFilter === 'super'} onClick={() => changeRoleFilter('super')}>超级管理员</Tag>
          <Tag active={roleFilter === 'ops'} onClick={() => changeRoleFilter('ops')}>运营管理员</Tag>
        </div>
      </div>

      {/* 表格 */}
      {loading ? <Spinner text="管理员加载中…" /> : (
        <Table
          rowKey="id"
          data={users as unknown as Record<string, unknown>[]}
          columns={[
            { key: 'id', title: 'ID', width: '60px', render: (r) => `#${r.id}` },
            { key: 'username', title: '账号', render: (r) => <span className={styles.account}>{String(r.username)}</span> },
            { key: 'name', title: '姓名', render: (r) => String(r.name) },
            { key: 'role', title: '角色', render: (r) => <RoleBadge role={String(r.role)} /> },
            { key: 'last_login_at', title: '最后登录', render: (r) => <span className={styles.time}>{String(r.last_login_at ?? '从未登录')}</span> },
            { key: 'is_active', title: '状态', render: (r) => <StatusBadge status={r.is_active ? 'active' : 'inactive'} /> },
            { key: 'ops', title: '操作', render: (r) => {
                const u = r as unknown as UserManageRow
                return (
                  <div className={styles.ops}>
                    <Button variant="text" size="sm" onClick={() => openEdit(u)}>编辑</Button>
                    <Button variant="text" size="sm" onClick={() => setResetModal(u)}>重置密码</Button>
                    {/* 超管账号无停用按钮（UI-UX §6.8） */}
                    {u.role !== 'super' && (
                      <Button variant="text" size="sm" onClick={() => toggleActive(u)}>{u.is_active ? '停用' : '启用'}</Button>
                    )}
                  </div>
                )
              } },
          ]}
        />
      )}

      <Pagination page={page} totalPages={totalPages} onChange={setPage} />

      {/* 权限说明提示条 */}
      <div className={styles.notice}>
        <span className={styles.noticeIcon} aria-hidden="true">ℹ️</span>
        <p className={styles.noticeText}>
          超级管理员可访问全部模块；运营管理员不显示"管理员管理"菜单；
          系统至少保留 1 个超管账号（停用/降级最后一名超管会被系统拦截）。
        </p>
      </div>

      {/* 新增 / 编辑弹窗 */}
      <UserModal open={modalOpen} onClose={() => setModalOpen(false)} editing={editing}
        onSaved={() => { setModalOpen(false); loadList() }} onToast={(t) => showToast(t.type, t.text)} />

      {/* 重置密码弹窗 */}
      <ResetModal target={resetModal} onClose={() => setResetModal(null)} onConfirm={doReset} />

      <Toast toast={toast} />
    </div>
  )
}

// ---------- 新增/编辑管理员弹窗 ----------
function UserModal({ open, onClose, editing, onSaved, onToast }: {
  open: boolean
  onClose: () => void
  editing: UserManageRow | null
  onSaved: () => void
  onToast: (t: { type: 'success' | 'error'; text: string }) => void
}) {
  const [username, setUsername] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'super' | 'ops'>('ops')
  const [isActive, setIsActive] = useState(true)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!open) return
    if (editing) {
      setUsername(editing.username); setName(editing.name)
      setPassword(''); setRole(editing.role); setIsActive(editing.is_active)
    } else {
      setUsername(''); setName(''); setPassword(''); setRole('ops'); setIsActive(true)
    }
    setErrors({})
  }, [open, editing])

  function validate(): boolean {
    const next: Record<string, string> = {}
    if (!/^[a-zA-Z0-9_]{3,20}$/.test(username.trim())) next.username = '账号需为 3-20 位字母/数字/下划线'
    if (name.trim().length < 2 || name.trim().length > 20) next.name = '姓名需为 2-20 个字符'
    if (!editing && (password.length < 6 || password.length > 20)) next.password = '密码需为 6-20 位'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function submit() {
    if (!validate() || saving) return
    setSaving(true)
    const payload: UserPayload = {
      username: username.trim(), name: name.trim(), role, is_active: isActive,
    }
    if (!editing) payload.password = password
    try {
      if (editing) {
        await client.put(`/users/${editing.id}`, payload)
        onToast({ type: 'success', text: '管理员信息已更新' })
      } else {
        await client.post('/users', payload)
        onToast({ type: 'success', text: '管理员已新增' })
      }
      onSaved()
    } catch (e) { onToast({ type: 'error', text: (e as Error).message }) }
    finally { setSaving(false) }
  }

  return (
    <Modal open={open} title={editing ? '编辑管理员' : '新增管理员'} onClose={onClose} width={560}
      footer={<>
        <Button variant="ghost" onClick={onClose}>取消</Button>
        <Button onClick={submit} disabled={saving}>{saving ? '保存中…' : '保存'}</Button>
      </>}>
      <div className={styles.formRow2}>
        <FormField label="账号" required error={errors.username} help={editing ? '账号不可修改' : '3-20 位字母/数字/下划线'}>
          <input className={`${styles.input} ${errors.username ? styles.inputError : ''}`} value={username} disabled={!!editing}
            maxLength={20}
            onChange={(e) => { setUsername(e.target.value); if (errors.username) setErrors((p) => ({ ...p, username: '' })) }} />
        </FormField>
        <FormField label="姓名" required error={errors.name}>
          <input className={`${styles.input} ${errors.name ? styles.inputError : ''}`} value={name} maxLength={20}
            onChange={(e) => { setName(e.target.value); if (errors.name) setErrors((p) => ({ ...p, name: '' })) }} />
        </FormField>
      </div>
      {!editing && (
        <FormField label="初始密码" required error={errors.password} help="6-20 位；创建后可由超管重置">
          <input className={`${styles.input} ${errors.password ? styles.inputError : ''}`} type="password" value={password}
            onChange={(e) => { setPassword(e.target.value); if (errors.password) setErrors((p) => ({ ...p, password: '' })) }} />
        </FormField>
      )}
      <FormField label="角色" required>
        <div className={styles.roleRow}>
          {(['super', 'ops'] as const).map((r) => (
            <button key={r} type="button"
              className={`${styles.roleBtn} ${role === r ? styles.roleActive : ''}`}
              onClick={() => setRole(r)}>
              {r === 'super' ? '超级管理员' : '运营管理员'}
            </button>
          ))}
        </div>
      </FormField>
      <FormField label="启用状态">
        <div className={styles.switchRow}>
          <Switch checked={isActive} onChange={setIsActive} label="启用状态" />
          <span className={styles.switchText}>{isActive ? '启用（可登录）' : '停用（无法登录）'}</span>
        </div>
      </FormField>
    </Modal>
  )
}

// ---------- 重置密码弹窗 ----------
function ResetModal({ target, onClose, onConfirm }: {
  target: UserManageRow | null
  onClose: () => void
  onConfirm: (p: string) => void
}) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { if (target) { setPassword(''); setError('') } }, [target])

  function confirm() {
    if (password.length < 6 || password.length > 20) {
      setError('密码需为 6-20 位')
      return
    }
    onConfirm(password)
  }

  return (
    <Modal open={!!target} title={`重置密码：${target?.name ?? ''}`} onClose={onClose} width={480}
      footer={<>
        <Button variant="ghost" onClick={onClose}>取消</Button>
        <Button onClick={confirm}>确认重置</Button>
      </>}>
      <p className={styles.resetHint}>重置后该管理员需使用新密码登录。</p>
      <FormField label="新密码" required error={error}>
        <input className={`${styles.input} ${error ? styles.inputError : ''}`} type="password" value={password}
          placeholder="6-20 位新密码" autoFocus
          onChange={(e) => { setPassword(e.target.value); if (error) setError('') }} />
      </FormField>
    </Modal>
  )
}
