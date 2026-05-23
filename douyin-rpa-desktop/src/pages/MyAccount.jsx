import { useState, useEffect } from 'react'
import { CreditCard, Clock, Zap, Shield, Loader, X, Eye, EyeOff } from 'lucide-react'

export default function MyAccount({ merchantData }) {
  const [account, setAccount] = useState(null)
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)

  // ★ 修改密码弹窗状态
  const [showPwdModal, setShowPwdModal] = useState(false)
  const [pwdForm, setPwdForm] = useState({ old: '', new: '', confirm: '' })
  const [pwdError, setPwdError] = useState('')
  const [pwdSuccess, setPwdSuccess] = useState('')
  const [pwdLoading, setPwdLoading] = useState(false)
  const [showOld, setShowOld] = useState(false)
  const [showNew, setShowNew] = useState(false)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [accRes, logsRes] = await Promise.all([
          fetch(`http://localhost:8100/api/account?merchant_id=${merchantData?.merchant_id || 0}`),
          fetch('http://localhost:8100/api/logs')
        ])
        const accData = await accRes.json()
        const logsData = await logsRes.json()
        setAccount(accData)
        setLogs(logsData)
      } catch (e) {
        console.error(e)
      }
      setLoading(false)
    }
    fetchData()
    const timer = setInterval(fetchData, 5000)
    return () => clearInterval(timer)
  }, [])

  // ★ 提交修改密码
  const handleChangePassword = async () => {
    setPwdError('')
    setPwdSuccess('')

    if (!pwdForm.old) { setPwdError('请输入原密码'); return }
    if (!pwdForm.new) { setPwdError('请输入新密码'); return }
    if (pwdForm.new.length < 6) { setPwdError('新密码至少 6 位'); return }
    if (pwdForm.new !== pwdForm.confirm) { setPwdError('两次输入的新密码不一致'); return }
    if (pwdForm.old === pwdForm.new) { setPwdError('新密码不能与原密码相同'); return }

    setPwdLoading(true)
    try {
      const res = await fetch('http://localhost:8100/api/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          merchant_id: merchantData?.merchant_id,
          old_password: pwdForm.old,
          new_password: pwdForm.new,
        })
      })
      const data = await res.json()
      if (res.ok) {
        setPwdSuccess('✅ 密码修改成功！下次登录请使用新密码')
        setPwdForm({ old: '', new: '', confirm: '' })
        setTimeout(() => setShowPwdModal(false), 2000)
      } else {
        setPwdError(data.error || '修改失败')
      }
    } catch (e) {
      setPwdError('网络错误，请稍后重试')
    }
    setPwdLoading(false)
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '50vh', color: 'var(--text-muted)' }}>
        <Loader size={24} /> <span style={{ marginLeft: 12 }}>正在从数据库加载账户信息...</span>
      </div>
    )
  }

  const balance = account?.balance ?? 0
  const merchantId = account?.merchant_id ?? '-'
  const merchantName = account?.phone || merchantData?.phone || '-'
  const status = account?.status
  const slotCount = account?.slot_count ?? 0
  const totalLeads = account?.total_leads ?? 0
  const createdAt = account?.created_at ?? '-'
  const statusText = status === 1 ? '正常' : status === 0 ? '未激活' : '已禁用'

  const inputStyle = {
    width: '100%', padding: '10px 12px', borderRadius: 8,
    border: '1px solid var(--border-color)', background: 'var(--bg-input)',
    fontSize: 14, outline: 'none', boxSizing: 'border-box',
  }

  return (
    <>
      <header className="page-header">
        <h1 className="page-title">我的账户</h1>
      </header>

      <div className="page-body">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '20px' }}>
          {/* 左侧 */}
          <div>
            {/* 商户信息 */}
            <div className="panel" style={{ marginBottom: 20 }}>
              <div className="panel-header">
                <span className="panel-title">📋 商户信息</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>数据来源: Supabase merchant 表</span>
              </div>
              <div className="panel-body">
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 20,
                  padding: '20px 0', borderBottom: '1px solid var(--border-color)', marginBottom: 20,
                }}>
                  <div style={{
                    width: 64, height: 64, borderRadius: 'var(--radius-lg)',
                    background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Shield size={28} color="white" />
                  </div>
                  <div>
                    <div style={{ fontSize: 22, fontWeight: 700 }}>{merchantName}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>内部ID: {merchantId}</div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      状态: <span style={{ color: status === 1 ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: 600 }}>{statusText}</span>
                    </div>
                  </div>
                  <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                    <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--accent-orange)' }}>
                      ¥{balance.toFixed(2)}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>剩余余额</div>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
                  <div style={{
                    background: 'var(--bg-input)', padding: 16, borderRadius: 'var(--radius-md)',
                    textAlign: 'center',
                  }}>
                    <CreditCard size={20} style={{ color: 'var(--accent-blue)', marginBottom: 8 }} />
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>RPA 槽位</div>
                    <div style={{ fontSize: 20, fontWeight: 700 }}>{slotCount}</div>
                  </div>
                  <div style={{
                    background: 'var(--bg-input)', padding: 16, borderRadius: 'var(--radius-md)',
                    textAlign: 'center',
                  }}>
                    <Clock size={20} style={{ color: 'var(--accent-orange)', marginBottom: 8 }} />
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>注册日期</div>
                    <div style={{ fontSize: 20, fontWeight: 700 }}>{createdAt}</div>
                  </div>
                  <div style={{
                    background: 'var(--bg-input)', padding: 16, borderRadius: 'var(--radius-md)',
                    textAlign: 'center',
                  }}>
                    <Zap size={20} style={{ color: 'var(--accent-green)', marginBottom: 8 }} />
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>总线索</div>
                    <div style={{ fontSize: 20, fontWeight: 700 }}>{totalLeads}</div>
                  </div>
                </div>
              </div>
            </div>

            {/* 操作日志 */}
            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">📝 系统日志</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>来自 RPA 运行时</span>
              </div>
              <div className="panel-body">
                <ul className="activity-feed">
                  {logs.length > 0 ? logs.map((log, i) => (
                    <li className="activity-item" key={i}>
                      <span className={`activity-dot ${log.type}`} />
                      <span className="activity-text">
                        <strong>[{log.action}]</strong> {log.detail}
                      </span>
                      <span className="activity-time">{log.time}</span>
                    </li>
                  )) : (
                    <li style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>暂无日志</li>
                  )}
                </ul>
              </div>
            </div>
          </div>

          {/* 右侧 */}
          <div>
            <div className="panel" style={{ marginBottom: 20 }}>
              <div className="panel-header">
                <span className="panel-title">⚡ 快捷操作</span>
              </div>
              <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <button className="btn btn-ghost" style={{ width: '100%', justifyContent: 'flex-start' }} onClick={() => { setShowPwdModal(true); setPwdError(''); setPwdSuccess(''); setPwdForm({ old: '', new: '', confirm: '' }) }}>
                  🔑 修改密码
                </button>
                <button className="btn btn-ghost" style={{ width: '100%', justifyContent: 'flex-start' }} onClick={() => alert('📱 绑定手机功能即将上线')}>
                  📱 绑定手机
                </button>
                <button className="btn btn-ghost" style={{ width: '100%', justifyContent: 'flex-start' }} onClick={() => alert('📧 邮件推送通知功能正在开发中')}>
                  📧 邮箱通知设置
                </button>
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <span className="panel-title">💬 联系客服</span>
              </div>
              <div className="panel-body" style={{ textAlign: 'center', padding: '24px 22px' }}>
                <div style={{ fontSize: 40, marginBottom: 12 }}>💁‍♀️</div>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>需要帮助？</div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
                  工作时间: 9:00 - 22:00
                </div>
                <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} onClick={() => alert('客服微信号：OrangeAI_Support\n\n请添加微信获取技术支持')}>
                  在线咨询
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ★ 修改密码弹窗 */}
      {showPwdModal && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 9999,
          background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => setShowPwdModal(false)}>
          <div style={{
            background: 'var(--bg-card)', borderRadius: 16, padding: '28px 32px',
            width: 400, maxWidth: '90vw',
            boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
          }} onClick={e => e.stopPropagation()}>
            {/* 标题 */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
              <div style={{ fontSize: 18, fontWeight: 700 }}>🔐 修改登录密码</div>
              <button onClick={() => setShowPwdModal(false)} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--text-muted)', padding: 4,
              }}><X size={18} /></button>
            </div>

            {/* 表单 */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, display: 'block', color: 'var(--text-secondary)' }}>原密码</label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showOld ? 'text' : 'password'}
                    placeholder="请输入当前密码"
                    value={pwdForm.old}
                    onChange={e => setPwdForm({ ...pwdForm, old: e.target.value })}
                    style={inputStyle}
                  />
                  <button onClick={() => setShowOld(!showOld)} style={{
                    position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                    background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2,
                  }}>{showOld ? <EyeOff size={16} /> : <Eye size={16} />}</button>
                </div>
              </div>

              <div>
                <label style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, display: 'block', color: 'var(--text-secondary)' }}>新密码</label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showNew ? 'text' : 'password'}
                    placeholder="至少 6 位"
                    value={pwdForm.new}
                    onChange={e => setPwdForm({ ...pwdForm, new: e.target.value })}
                    style={inputStyle}
                  />
                  <button onClick={() => setShowNew(!showNew)} style={{
                    position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                    background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2,
                  }}>{showNew ? <EyeOff size={16} /> : <Eye size={16} />}</button>
                </div>
              </div>

              <div>
                <label style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, display: 'block', color: 'var(--text-secondary)' }}>确认新密码</label>
                <input
                  type="password"
                  placeholder="再次输入新密码"
                  value={pwdForm.confirm}
                  onChange={e => setPwdForm({ ...pwdForm, confirm: e.target.value })}
                  onKeyDown={e => e.key === 'Enter' && handleChangePassword()}
                  style={inputStyle}
                />
              </div>

              {/* 错误/成功提示 */}
              {pwdError && (
                <div style={{
                  padding: '10px 14px', borderRadius: 8,
                  background: '#fef2f2', color: '#b91c1c',
                  fontSize: 13, fontWeight: 500,
                }}>❌ {pwdError}</div>
              )}
              {pwdSuccess && (
                <div style={{
                  padding: '10px 14px', borderRadius: 8,
                  background: '#f0fdf4', color: '#15803d',
                  fontSize: 13, fontWeight: 500,
                }}>{pwdSuccess}</div>
              )}

              <button
                className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center', marginTop: 4, padding: '12px 0' }}
                onClick={handleChangePassword}
                disabled={pwdLoading}
              >
                {pwdLoading ? '修改中...' : '确认修改'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
