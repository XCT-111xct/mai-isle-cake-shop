// ============================================================
// 文件功能：留言管理（UI-UX §6.7，PRD F14）
// 功能：列表筛选/搜索、详情查看、标记已处理↔未处理、删除
// 说明：留言由前台表单产生，后台不可新增
// ============================================================

import { useCallback, useEffect, useState } from 'react'
import { client } from '@/api/client'
import type { MessageRow, PageResult } from '@/api/types'
import {
  PageHeader, Table, Modal, StatusBadge, Tag, Pagination, Toast, Spinner,
} from '@/components/AdminComponents'
import { Button, SearchInput, Select } from '@/components/AdminForm'
import { formatDateTime } from '@/utils/datetime'
import styles from './MessagePage.module.css'

export default function MessagePage() {
  const [messages, setMessages] = useState<MessageRow[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(12)
  const [statusFilter, setStatusFilter] = useState<'all' | 'pending' | 'done'>('all')
  const [keyword, setKeyword] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  const [viewing, setViewing] = useState<MessageRow | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  function showToast(type: 'success' | 'error', text: string) {
    setToast({ type, text })
    setTimeout(() => setToast(null), 4000)
  }

  const loadList = useCallback(() => {
    setLoading(true)
    client.get('/messages', {
      params: { status: statusFilter === 'all' ? undefined : statusFilter, keyword: search || undefined, page, page_size: pageSize },
    })
      .then((r) => {
        const d = r.data.data as PageResult<MessageRow>
        setMessages(d.items); setTotal(d.total); setTotalPages(d.total_pages)
      })
      .catch(() => { setMessages([]); setTotal(0) })
      .finally(() => setLoading(false))
  }, [statusFilter, search, page, pageSize])

  useEffect(() => { loadList() }, [loadList])

  function changeStatusFilter(s: string) { setStatusFilter(s as 'all' | 'pending' | 'done'); setPage(1) }
  function doSearch() { setSearch(keyword); setPage(1) }

  // 查看详情（完整手机号）
  function openView(m: MessageRow) {
    client.get(`/messages/${m.id}`).then((r) => setViewing(r.data.data as MessageRow)).catch((e) => showToast('error', (e as Error).message))
  }

  // 标记已处理 / 未处理
  async function toggleStatus(m: MessageRow) {
    try {
      await client.patch(`/messages/${m.id}/status`, { status: m.status === 'done' ? 'pending' : 'done' })
      showToast('success', m.status === 'done' ? '已标记为未处理' : '已标记为已处理')
      loadList()
    } catch (e) { showToast('error', (e as Error).message) }
  }

  // 删除
  async function remove(m: MessageRow) {
    if (!window.confirm(`确认删除留言 #${m.id}（${m.name}）？此操作不可恢复`)) return
    try {
      await client.delete(`/messages/${m.id}`)
      showToast('success', '留言已删除')
      loadList()
    } catch (e) { showToast('error', (e as Error).message) }
  }

  return (
    <div>
      <PageHeader meta="MESSAGES · 留言管理" title="留言管理" />

      {/* 工具栏 */}
      <div className={styles.toolbar}>
        <div className={styles.filters}>
          <Tag active={statusFilter === 'all'} onClick={() => changeStatusFilter('all')}>全部</Tag>
          <Tag active={statusFilter === 'pending'} onClick={() => changeStatusFilter('pending')}>未处理</Tag>
          <Tag active={statusFilter === 'done'} onClick={() => changeStatusFilter('done')}>已处理</Tag>
        </div>
        <div className={styles.toolRight}>
          <SearchInput value={keyword} onChange={setKeyword} onSearch={doSearch} placeholder="搜索姓名 / 电话" />
          <Select
            value={statusFilter === 'all' ? '' : statusFilter}
            onChange={changeStatusFilter}
            placeholder="全部状态"
            ariaLabel="按状态筛选"
            options={[{ value: 'pending', label: '未处理' }, { value: 'done', label: '已处理' }]}
          />
        </div>
      </div>

      {/* 表格 */}
      {loading ? <Spinner text="留言加载中…" /> : (
        <Table
          rowKey="id"
          data={messages as unknown as Record<string, unknown>[]}
          columns={[
            { key: 'id', title: 'ID', width: '70px', render: (r) => `#${r.id}` },
            { key: 'name', title: '姓名', render: (r) => String(r.name) },
            { key: 'phone', title: '联系电话', render: (r) => <span className={styles.phone}>{String(r.phone)}</span> },
            { key: 'content', title: '留言预览', render: (r) => <span className={styles.preview} title={String(r.content)}>{String(r.content)}</span> },
            { key: 'created_at', title: '提交时间', render: (r) => <span className={styles.time}>{formatDateTime(String(r.created_at))}</span> },
            { key: 'status', title: '状态', render: (r) => <StatusBadge status={String(r.status)} /> },
            { key: 'ops', title: '操作', render: (r) => {
                const m = r as unknown as MessageRow
                return (
                  <div className={styles.ops}>
                    <Button variant="text" size="sm" onClick={() => openView(m)}>查看</Button>
                    <Button variant="text" size="sm" onClick={() => toggleStatus(m)}>
                      {m.status === 'done' ? '标记未处理' : '标记已处理'}
                    </Button>
                    <Button variant="text" size="sm" onClick={() => remove(m)}>删除</Button>
                  </div>
                )
              } },
          ]}
        />
      )}

      <Pagination page={page} totalPages={totalPages} onChange={setPage} />

      {/* 详情弹窗（完整手机号） */}
      <Modal open={!!viewing} title={`留言详情 #${viewing?.id}`} onClose={() => setViewing(null)}>
        {viewing && (
          <div className={styles.detail}>
            <div className={styles.detailRow}>
              <span className={styles.detailLabel}>姓名</span>
              <span>{viewing.name}</span>
            </div>
            <div className={styles.detailRow}>
              <span className={styles.detailLabel}>联系电话</span>
              <span>{viewing.phone}</span>
            </div>
            <div className={styles.detailRow}>
              <span className={styles.detailLabel}>提交时间</span>
              <span>{formatDateTime(viewing.created_at)}</span>
            </div>
            <div className={styles.detailRow}>
              <span className={styles.detailLabel}>状态</span>
              <StatusBadge status={viewing.status} />
            </div>
            <div className={styles.detailContent}>
              <span className={styles.detailLabel}>留言内容</span>
              <p className={styles.detailText}>{viewing.content}</p>
            </div>
          </div>
        )}
      </Modal>

      <Toast toast={toast} />
    </div>
  )
}
