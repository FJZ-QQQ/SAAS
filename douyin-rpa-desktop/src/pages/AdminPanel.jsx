import { useState, useEffect } from 'react'
import { Users, DollarSign, Power, PowerOff, Search, RefreshCw, LogOut, Shield, Target, Loader } from 'lucide-react'

export default function AdminPanel({ adminData, onLogout }) {
  const [merchants, setMerchants] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [balanceModal, setBalanceModal] = useState(null)
  const [newBalance, setNewBalance] = useState('')
  const [actionLoading, setActionLoading] = useState(null)
  const adminToken = adminData?.admin_token || ''

  const authHeaders = () => ({
    Authorization: `Bearer ${adminToken}`
  })

  const handleAuthError = (res) => {
    if (res.status === 401) {
      onLogout?.()
      return true
    }
    return false
  }

  const fetchMerchants = async () => {
    if (!adminToken) {
      setLoading(false)
      onLogout?.()
      return
    }
    try {
      const res = await fetch('http://localhost:8100/api/admin/merchants', {
        headers: authHeaders()
      })
      if (handleAuthError(res)) return
      const data = await res.json()
      setMerchants(Array.isArray(data) ? data : [])
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchMerchants()
    const timer = setInterval(fetchMerchants, 5000)
    return () => clearInterval(timer)
  }, [adminToken])

  const handleSetBalance = async () => {
    if (!balanceModal || newBalance === '') return
    setActionLoading(balanceModal.id)
    try {
      const res = await fetch('http://localhost:8100/api/admin/balance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ merchant_id: balanceModal.id, balance: parseFloat(newBalance) })
      })
      if (handleAuthError(res)) return
      setBalanceModal(null)
      setNewBalance('')
      fetchMerchants()
    } catch (e) {
      console.error(e)
    }
    setActionLoading(null)
  }

  const handleToggle = async (merchant) => {
    const newStatus = merchant.status === 1 ? 0 : 1
    const action = newStatus === 1 ? '启用' : '停用'
    if (!confirm(`确定要${action}商户 ${merchant.phone} 吗？`)) return
    setActionLoading(merchant.id)
    try {
      const res = await fetch('http://localhost:8100/api/admin/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ merchant_id: merchant.id, status: newStatus })
      })
      if (handleAuthError(res)) return
      fetchMerchants()
    } catch (e) {
      console.error(e)
    }
    setActionLoading(null)
  }

  const filtered = merchants.filter(m =>
    !searchTerm ||
    m.phone.includes(searchTerm) ||
    String(m.id).includes(searchTerm)
  )

  const totalMerchants = merchants.length
  const activeMerchants = merchants.filter(m => m.status === 1).length
  const totalBalance = merchants.reduce((sum, m) => sum + m.balance, 0)
  const totalLeads = merchants.reduce((sum, m) => sum + (m.lead_count || 0), 0)

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0f172a',
      color: '#f1f5f9',
      fontFamily: 'Inter, system-ui, sans-serif',
    }}>
      {/* 顶部导航 */}
      <header style={{
        height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 28px', borderBottom: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(15, 23, 42, 0.8)', backdropFilter: 'blur(10px)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Shield size={18} color="white" />
          </div>
          <span style={{ fontWeight: 700, fontSize: 16 }}>光宸智能客服</span>
          <span style={{
            padding: '2px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
            background: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa',
          }}>管理员</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            onClick={fetchMerchants}
            style={{
              background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 8, padding: '8px 16px', color: '#94a3b8', fontSize: 13,
              cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            <RefreshCw size={14} /> 刷新
          </button>
          <button
            onClick={onLogout}
            style={{
              background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)',
              borderRadius: 8, padding: '8px 16px', color: '#f87171', fontSize: 13,
              cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
            }}
          >
            <LogOut size={14} /> 退出
          </button>
        </div>
      </header>

      <div style={{ padding: '24px 28px', maxWidth: 1200, margin: '0 auto' }}>
        {/* 统计卡片 */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
          {[
            { label: '总商家数', value: totalMerchants, icon: Users, color: '#3b82f6', bg: 'rgba(59, 130, 246, 0.1)' },
            { label: '活跃商家', value: activeMerchants, icon: Power, color: '#10b981', bg: 'rgba(16, 185, 129, 0.1)' },
            { label: '总余额 (¥)', value: totalBalance.toFixed(0), icon: DollarSign, color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.1)' },
            { label: '总客资数', value: totalLeads, icon: Target, color: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.1)' },
          ].map((s, i) => {
            const Icon = s.icon
            return (
              <div key={i} style={{
                background: 'rgba(30, 41, 59, 0.6)', border: '1px solid rgba(255,255,255,0.06)',
                borderRadius: 14, padding: 22, position: 'relative',
              }}>
                <div style={{
                  position: 'absolute', top: 18, right: 18, width: 40, height: 40,
                  borderRadius: 10, background: s.bg, display: 'flex',
                  alignItems: 'center', justifyContent: 'center',
                }}>
                  <Icon size={20} color={s.color} />
                </div>
                <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 8 }}>{s.label}</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: '#f1f5f9' }}>{s.value}</div>
              </div>
            )
          })}
        </div>

        {/* 搜索栏 */}
        <div style={{ marginBottom: 20, position: 'relative', maxWidth: 400 }}>
          <Search size={16} style={{
            position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)',
            color: '#475569'
          }} />
          <input
            placeholder="搜索商家（手机号/ID）..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            style={{
              width: '100%', padding: '12px 16px 12px 40px',
              background: 'rgba(30, 41, 59, 0.6)', border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 10, fontSize: 14, color: '#f1f5f9',
              outline: 'none', boxSizing: 'border-box',
            }}
          />
        </div>

        {/* 商家列表 */}
        <div style={{
          background: 'rgba(30, 41, 59, 0.6)', border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: 14, overflow: 'hidden',
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                {['ID', '手机号', '余额', '客资数', '状态', '注册时间', '操作'].map(h => (
                  <th key={h} style={{
                    textAlign: 'left', padding: '14px 16px', fontSize: 12,
                    fontWeight: 600, color: '#64748b', textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
                  <Loader size={20} /> 加载中...
                </td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={7} style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
                  {searchTerm ? '没有匹配的商家' : '暂无商家数据'}
                </td></tr>
              ) : filtered.map(m => (
                <tr key={m.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <td style={{ padding: '14px 16px', fontSize: 14, fontWeight: 600, color: '#94a3b8' }}>#{m.id}</td>
                  <td style={{ padding: '14px 16px', fontSize: 14, color: '#f1f5f9', fontFamily: 'monospace' }}>{m.phone}</td>
                  <td style={{ padding: '14px 16px', fontSize: 14, fontWeight: 700, color: m.balance > 0 ? '#fbbf24' : '#ef4444' }}>
                    ¥{m.balance.toFixed(2)}
                  </td>
                  <td style={{ padding: '14px 16px', fontSize: 14, color: '#94a3b8' }}>{m.lead_count || 0}</td>
                  <td style={{ padding: '14px 16px' }}>
                    <span style={{
                      padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                      background: m.status === 1 ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
                      color: m.status === 1 ? '#34d399' : '#f87171',
                    }}>
                      {m.status === 1 ? '启用' : '停用'}
                    </span>
                  </td>
                  <td style={{ padding: '14px 16px', fontSize: 13, color: '#64748b' }}>{m.created_at}</td>
                  <td style={{ padding: '14px 16px' }}>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        onClick={() => { setBalanceModal(m); setNewBalance(String(m.balance)) }}
                        disabled={actionLoading === m.id}
                        style={{
                          background: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.2)',
                          borderRadius: 6, padding: '5px 12px', color: '#60a5fa', fontSize: 12,
                          cursor: 'pointer', fontWeight: 600,
                        }}
                      >
                        <DollarSign size={12} style={{ verticalAlign: 'middle', marginRight: 2 }} />
                        余额
                      </button>
                      <button
                        onClick={() => handleToggle(m)}
                        disabled={actionLoading === m.id}
                        style={{
                          background: m.status === 1 ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.1)',
                          border: `1px solid ${m.status === 1 ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)'}`,
                          borderRadius: 6, padding: '5px 12px',
                          color: m.status === 1 ? '#f87171' : '#34d399',
                          fontSize: 12, cursor: 'pointer', fontWeight: 600,
                        }}
                      >
                        {m.status === 1 ? <><PowerOff size={12} style={{ verticalAlign: 'middle', marginRight: 2 }} />停用</> :
                          <><Power size={12} style={{ verticalAlign: 'middle', marginRight: 2 }} />启用</>}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 余额设置弹窗 */}
      {balanceModal && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.7)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }} onClick={() => setBalanceModal(null)}>
          <div style={{
            background: '#1e293b', borderRadius: 16, padding: 32,
            width: 400, border: '1px solid rgba(255,255,255,0.1)',
            boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
          }} onClick={e => e.stopPropagation()}>
            <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6, color: '#f1f5f9' }}>
              设置余额
            </h3>
            <p style={{ fontSize: 13, color: '#64748b', marginBottom: 24 }}>
              商户 {balanceModal.phone} · 内部ID {balanceModal.id}
            </p>

            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#94a3b8', marginBottom: 8 }}>
                新余额（元）
              </label>
              <input
                type="number"
                value={newBalance}
                onChange={e => setNewBalance(e.target.value)}
                style={{
                  width: '100%', padding: '14px 16px',
                  background: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 10, fontSize: 20, fontWeight: 700, color: '#fbbf24',
                  outline: 'none', boxSizing: 'border-box', textAlign: 'center',
                }}
                autoFocus
              />
              <p style={{ fontSize: 12, color: '#64748b', marginTop: 8, textAlign: 'center' }}>
                当前余额：¥{balanceModal.balance.toFixed(2)}
              </p>
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <button
                onClick={() => setBalanceModal(null)}
                style={{
                  flex: 1, padding: '12px', background: 'rgba(255,255,255,0.06)',
                  border: '1px solid rgba(255,255,255,0.1)', borderRadius: 10,
                  color: '#94a3b8', fontSize: 14, fontWeight: 600, cursor: 'pointer',
                }}
              >取消</button>
              <button
                onClick={handleSetBalance}
                style={{
                  flex: 1, padding: '12px', background: '#3b82f6',
                  border: 'none', borderRadius: 10,
                  color: 'white', fontSize: 14, fontWeight: 600, cursor: 'pointer',
                }}
              >确认设置</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
