import { useState, useEffect } from 'react'
import { Plus, Power, RefreshCw, Trash2, QrCode, X, Loader } from 'lucide-react'

const formatStoreName = (id) => `${id}号店铺`

export default function Accounts({ merchantData }) {
  const [liveAccounts, setLiveAccounts] = useState({})
  const [loadingMsg, setLoadingMsg] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)
  const [newMid, setNewMid] = useState('')
  const [addError, setAddError] = useState('')
  const [adding, setAdding] = useState(false)

  const currentMid = merchantData?.merchant_id ? String(merchantData.merchant_id) : ''

  const nextSlotId = () => {
    const used = new Set(Object.keys(liveAccounts).map(id => Number(id)).filter(Boolean))
    let next = 1
    while (used.has(next)) next += 1
    return String(next)
  }

  const openAddModal = () => {
    setNewMid(nextSlotId())
    setShowAddModal(true)
  }

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const qs = currentMid ? `?owner_merchant_id=${currentMid}` : ''
        const res = await fetch(`http://localhost:8100/status${qs}`)
        const data = await res.json()
        setLiveAccounts(data)
      } catch (e) {
        // Backend not ready
      }
    }
    fetchStatus()
    const timer = setInterval(fetchStatus, 2000)
    return () => clearInterval(timer)
  }, [currentMid])

  // 自动监测绑定成功状态，如果成功则自动关闭弹窗
  useEffect(() => {
    if (adding && newMid && liveAccounts[newMid]) {
      const status = liveAccounts[newMid].status
      if (status === 'bound' || status === 'running') {
        setShowAddModal(false)
        setAdding(false)
        setNewMid('')
        setAddError('')
      }
    }
  }, [liveAccounts, adding, newMid])

  const handleAddAccount = async () => {
    if (!currentMid) {
      setAddError('当前登录商户信息缺失，请重新登录')
      return
    }
    const bindMid = String(newMid || '').trim()
    if (!bindMid || !/^\d+$/.test(bindMid) || Number(bindMid) <= 0) {
      setAddError('请输入正确的店铺编号，例如 1、2、3')
      return
    }
    setAdding(true)
    setAddError('')
    setNewMid(bindMid)
    setLoadingMsg(`正在启动绑定浏览器... 店铺 ${bindMid}`)
    try {
      const res = await fetch('http://localhost:8100/slot/bind', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ owner_merchant_id: Number(currentMid), slot_id: Number(bindMid) })
      })
      const data = await res.json()
      if (!res.ok || data.status === 'error') {
        setAddError(data.error || data.message || '绑定失败')
      } else if (data.status === 'already_logged_in') {
        setShowAddModal(false)
        setNewMid('')
        setAddError('')
      } else if (data.status === 'waiting_scan') {
        setLoadingMsg('等待在弹出的浏览器中完成登录...')
        // 不关闭弹窗，等待用户操作或点击 X 取消
        return
      } else {
        setShowAddModal(false)
        setNewMid('')
        setAddError('')
      }
    } catch (e) {
      setAddError('请求失败: ' + e.message)
    }
    setAdding(false)
    setLoadingMsg('')
  }

  const handleStart = async (mid) => {
    try {
      const res = await fetch('http://localhost:8100/slot/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ owner_merchant_id: Number(currentMid), slot_id: Number(mid) })
      })
      if (!res.ok) throw new Error((await res.json()).error || '启动请求失败')
    } catch (e) {
      console.error('启动失败:', e)
      alert('启动失败: ' + e.message)
    }
  }

  const handleStop = async (mid) => {
    try {
      const res = await fetch('http://localhost:8100/slot/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ owner_merchant_id: Number(currentMid), slot_id: Number(mid) })
      })
      if (!res.ok) throw new Error((await res.json()).error || '停止请求失败')
    } catch (e) {
      console.error('停止失败:', e)
      alert('停止失败: ' + e.message)
    }
  }

  const handleDelete = async (mid) => {
    if (!window.confirm(`确定要彻底删除店铺 ${mid} 吗？\n该操作将清除该店铺的浏览器缓存与登录状态。`)) return
    try {
      const res = await fetch('http://localhost:8100/slot/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ owner_merchant_id: Number(currentMid), slot_id: Number(mid) })
      })
      if (!res.ok) throw new Error((await res.json()).error || '删除请求失败')
    } catch (e) {
      console.error('删除失败:', e)
      alert('删除失败: ' + e.message)
    }
  }

  // Convert the object mapping to an array
  const accountsList = Object.entries(liveAccounts)
    .map(([mid, data]) => ({
    id: mid,
    name: formatStoreName(mid),
    emoji: data.status === 'running' ? '⚡' : data.status === 'login_expired' ? '🔑' : '💤',
    status: data.status === 'running' ? 'online' 
      : data.status === 'login_expired' ? 'warning'
      : (data.status === 'error' ? 'error' : 'offline'),
    rawStatus: data.status,
    detail: data.status,
    replies: data.total_messages || 0,
    leads: data.total_leads || 0,
    lastHeartbeat: data.last_heartbeat,
    lastError: data.last_error,
    recoveryCount: data.recovery_count || 0,
  }))

  const formatHeartbeat = (isoStr) => {
    if (!isoStr) return null
    try {
      const d = new Date(isoStr)
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch { return null }
  }

  return (
    <>
      <header className="page-header">
        <h1 className="page-title">账号管理</h1>
        <button className="btn btn-primary" onClick={openAddModal}>
          <Plus size={16} />
          添加账号
        </button>
      </header>

      <div className="page-body">
        {loadingMsg && <div style={{ marginBottom: 20, color: 'var(--accent-orange)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Loader size={16} className="spin" /> {loadingMsg}
        </div>}
        
        <div className="account-grid">
          {accountsList.map(acc => (
            <div className="account-card" key={acc.id}>
              <div className="account-avatar">
                {acc.emoji}
                <span className={`status-dot ${acc.status}`} />
              </div>
              <div className="account-name">{acc.name}</div>
              <div className={`account-status ${acc.status}`}>
                {acc.status === 'online' ? '● 在线运行中' 
                  : acc.status === 'warning' ? '● 登录已过期'
                  : acc.status === 'error' ? '● 异常' 
                  : `● ${acc.rawStatus}`}
              </div>
              
              {/* 健康信息 */}
              {acc.status === 'online' && acc.lastHeartbeat && (
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center', marginTop: 4 }}>
                  最后心跳: {formatHeartbeat(acc.lastHeartbeat)}
                  {acc.recoveryCount > 0 && <span style={{ color: 'var(--accent-orange)', marginLeft: 6 }}>已恢复{acc.recoveryCount}次</span>}
                </div>
              )}
              
              {/* 错误提示 */}
              {acc.lastError && (
                <div style={{
                  fontSize: 11, color: 'var(--accent-red)', textAlign: 'center',
                  marginTop: 6, padding: '6px 10px', borderRadius: 8,
                  background: 'rgba(239,68,68,0.08)', lineHeight: 1.5,
                }}>
                  {acc.lastError}
                </div>
              )}

              <div style={{
                display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px',
                margin: '16px 0 14px', padding: '12px 0',
                borderTop: '1px solid var(--border-color)', borderBottom: '1px solid var(--border-color)',
              }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>回复</div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{acc.replies}</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>线索</div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--accent-orange)' }}>{acc.leads}</div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                {acc.status === 'online' ? (
                  <button className="btn btn-ghost" onClick={() => handleStop(acc.id)} style={{ padding: '6px 10px', fontSize: 12, color: 'var(--accent-red)' }} title="停止">
                    <Power size={14} /> 停止
                  </button>
                ) : acc.status === 'warning' ? (
                  <button className="btn btn-ghost" onClick={() => handleStart(acc.id)} style={{ padding: '6px 10px', fontSize: 12, color: 'var(--accent-orange)' }} title="重新登录">
                    <RefreshCw size={14} /> 重新登录
                  </button>
                ) : (
                  <button className="btn btn-ghost" onClick={() => handleStart(acc.id)} style={{ padding: '6px 10px', fontSize: 12, color: 'var(--accent-green)' }} title="启动">
                    <Power size={14} /> 启动
                  </button>
                )}
                <button className="btn btn-ghost" onClick={() => handleDelete(acc.id)} style={{ padding: '6px 10px', fontSize: 12, color: 'var(--accent-red)' }}>
                  <Trash2 size={14} /> 删除
                </button>
              </div>
            </div>
          ))}

          <div className="account-card add-new" onClick={openAddModal}>
            <Plus size={32} />
            <span style={{ fontSize: 14, fontWeight: 600 }}>添加店铺账号</span>
            <span style={{ fontSize: 12 }}>扫码登录抖音号</span>
          </div>
        </div>
      </div>

      {/* 添加账号弹窗 */}
      {showAddModal && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }} onClick={() => {
          if (adding && newMid) {
            fetch('http://localhost:8100/slot/delete', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ owner_merchant_id: Number(currentMid), slot_id: Number(newMid) })
            }).catch(() => {})
          }
          setShowAddModal(false)
          setAddError('')
          setNewMid('')
          setAdding(false)
        }}>
          <div style={{
            background: 'var(--bg-panel)', borderRadius: 16, padding: 32,
            width: 400, boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
            border: '1px solid var(--border-color)',
          }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
              <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>添加抖音账号</h2>
              <button className="btn btn-ghost" onClick={() => {
                if (adding && newMid) {
                  fetch('http://localhost:8100/slot/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ owner_merchant_id: Number(currentMid), slot_id: Number(newMid) })
                  }).catch(() => {})
                }
                setShowAddModal(false)
                setAddError('')
                setNewMid('')
                setAdding(false)
              }} style={{ padding: 4 }}>
                <X size={18} />
              </button>
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
                当前商户
              </label>
              <div className="form-input" style={{ width: '100%', display: 'flex', alignItems: 'center', color: 'var(--text-primary)' }}>
                {merchantData?.phone || '当前登录商户'}{currentMid ? ` · 内部ID ${currentMid}` : ''}
              </div>
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
                店铺编号
              </label>
              <input
                className="form-input"
                value={newMid}
                onChange={e => setNewMid(e.target.value.replace(/[^\d]/g, ''))}
                disabled={adding}
                placeholder="例如 1、2、3"
                style={{ width: '100%' }}
              />
            </div>

            <div style={{
              background: 'var(--bg-input)', padding: 14, borderRadius: 10,
              marginBottom: 20, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6
            }}>
              💡 <strong>操作步骤：</strong><br/>
              1. 填写店铺编号后点击"开始绑定"<br/>
              2. 系统会弹出一个浏览器窗口<br/>
              3. 在弹出的浏览器中扫码登录你的抖音号<br/>
              4. 登录成功后回到这里点击"启动"
            </div>

            {addError && (
              <div style={{
                background: '#fef2f2', color: '#ef4444', padding: '10px 14px',
                borderRadius: 8, fontSize: 13, marginBottom: 16, fontWeight: 500
              }}>
                {addError}
              </div>
            )}

            <div style={{ display: 'flex', gap: 10 }}>
              <button
                className="btn btn-ghost"
                onClick={() => {
                  if (adding && newMid) {
                    // 后台强制清理残留的浏览器进程
                    fetch('http://localhost:8100/slot/delete', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ owner_merchant_id: Number(currentMid), slot_id: Number(newMid) })
                    }).catch(() => {})
                  }
                  setShowAddModal(false)
                  setAddError('')
                  setNewMid('')
                  setAdding(false)
                }}
                style={{ flex: 1, justifyContent: 'center' }}
              >
                取消
              </button>
              <button
                className="btn btn-primary"
                onClick={handleAddAccount}
                disabled={adding}
                style={{ flex: 1, justifyContent: 'center' }}
              >
                {adding ? <><Loader size={14} className="spin" /> 请在浏览器操作...</> : <><QrCode size={14} /> 开始绑定</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
