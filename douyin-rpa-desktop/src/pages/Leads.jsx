import { useState, useEffect } from 'react'
import { Search, Phone, MessageCircle, Loader, Download } from 'lucide-react'

export default function Leads({ merchantData }) {
  const [leads, setLeads] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const mid = merchantData?.merchant_id || 0

  const getAuthHeaders = () => {
    let token = merchantData?.token || ''
    if (!token) {
      try {
        token = JSON.parse(localStorage.getItem('gc_session') || '{}')?.token || ''
      } catch {
        token = ''
      }
    }
    return token ? { Authorization: `Bearer ${token}` } : {}
  }

  const fetchLeads = () => {
    fetch(`http://localhost:8100/api/leads?merchant_id=${mid}`, { headers: getAuthHeaders() })
      .then(r => r.json())
      .then(data => { setLeads(data); setLoading(false) })
      .catch(e => { console.error(e); setLoading(false) })
  }

  useEffect(() => {
    fetchLeads()
    const timer = setInterval(fetchLeads, 10000)
    return () => clearInterval(timer)
  }, [mid])

  // 搜索过滤
  const filtered = leads.filter(l =>
    !searchTerm ||
    (l.user || '').includes(searchTerm) ||
    (l.value || '').includes(searchTerm) ||
    (l.source || '').includes(searchTerm)
  )

  // 统计
  const totalCount = leads.length
  const phoneCount = leads.filter(l => l.type === '手机号').length
  const wechatCount = leads.filter(l => l.type === '微信号').length

  const handleExport = async () => {
    try {
      // 在客户端直接生成 CSV（避免 Electron 下载问题）
      const BOM = '\uFEFF'
      const header = '序号,抖音昵称,联系方式,类型,来源,时间,状态\n'
      const rows = leads.map((l, i) => {
        // ★ 时间列加 \t 前缀，强制 Excel 当文本显示（防止 ########）
        const timeStr = l.time || ''
        return `${i+1},"${l.user || ''}","${l.value || ''}","${l.type || ''}","${l.source || ''}","\t${timeStr}","${l.status || ''}"`
      }).join('\n')
      const csv = BOM + header + rows
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `客资导出_${new Date().toISOString().slice(0,10)}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      alert('导出失败: ' + e.message)
    }
  }

  return (
    <>
      <header className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title">我的客资</h1>
        <button
          onClick={handleExport}
          disabled={leads.length === 0}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '8px 18px', borderRadius: 10, fontSize: 13, fontWeight: 600,
            background: leads.length > 0 ? 'var(--accent-orange)' : 'var(--bg-tertiary)',
            color: leads.length > 0 ? '#fff' : 'var(--text-muted)',
            border: 'none', cursor: leads.length > 0 ? 'pointer' : 'default',
            transition: 'all 0.2s',
          }}
          onMouseOver={e => { if(leads.length > 0) e.currentTarget.style.opacity = '0.85' }}
          onMouseOut={e => { e.currentTarget.style.opacity = '1' }}
        >
          <Download size={14} />
          导出 CSV
        </button>
      </header>

      <div className="page-body">
        {/* 统计摘要 */}
        <div className="stat-cards" style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginBottom: 24 }}>
          <div className="stat-card orange">
            <div className="stat-label">总客资数</div>
            <div className="stat-value">{totalCount}</div>
          </div>
          <div className="stat-card blue">
            <div className="stat-label">📱 手机号</div>
            <div className="stat-value">{phoneCount}</div>
          </div>
          <div className="stat-card purple">
            <div className="stat-label">💬 微信号</div>
            <div className="stat-value">{wechatCount}</div>
          </div>
        </div>

        {/* 搜索栏 */}
        <div style={{ marginBottom: 20, position: 'relative', maxWidth: 400 }}>
          <Search size={16} style={{
            position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-muted)'
          }} />
          <input
            className="form-input"
            placeholder="搜索客资（昵称、联系方式）..."
            style={{ paddingLeft: 40 }}
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
          />
        </div>

        {/* 客资表格 — 按文档要求：客户抖音昵称、联系方式、创建时间 */}
        <div className="panel">
          <table className="data-table">
            <thead>
              <tr>
                <th>客户抖音昵称</th>
                <th>联系方式类型</th>
                <th>联系方式</th>
                <th>来源账号</th>
                <th>收集时间</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                  <Loader size={18} style={{ marginRight: 8, verticalAlign: 'middle' }} />
                  正在从数据库加载...
                </td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={5} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                  {searchTerm ? '没有匹配的搜索结果' : (
                    <div>
                      <div style={{ fontSize: 32, marginBottom: 12 }}>📋</div>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>暂无客资数据</div>
                      <div style={{ fontSize: 12 }}>当AI收集到客户的手机号或微信号时，会自动显示在这里</div>
                    </div>
                  )}
                </td></tr>
              ) : filtered.map(lead => (
                <tr key={lead.id}>
                  <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                    {lead.user || '未知用户'}
                  </td>
                  <td>
                    <span style={{
                      padding: '4px 12px', borderRadius: 20,
                      fontSize: 12, fontWeight: 600,
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      background: lead.type === '手机号' ? 'var(--accent-blue-glow)' : 'var(--accent-purple-glow)',
                      color: lead.type === '手机号' ? 'var(--accent-blue)' : 'var(--accent-purple)',
                    }}>
                      {lead.type === '手机号' ? <Phone size={12} /> : <MessageCircle size={12} />}
                      {lead.type}
                    </span>
                  </td>
                  <td style={{ fontWeight: 700, color: 'var(--text-primary)', fontFamily: 'monospace', fontSize: 15 }}>
                    {lead.value}
                  </td>
                  <td style={{ color: 'var(--text-secondary)' }}>{lead.source}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{lead.time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
