import { useState } from 'react'
import { Shield, User, Lock, ArrowRight, ArrowLeft } from 'lucide-react'

export default function AdminLogin({ onLogin, onBack }) {
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!account || !password) { setError('请输入账号和密码'); return }
    setLoading(true)

    try {
      const res = await fetch('http://localhost:8100/api/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account, password })
      })
      const data = await res.json()
      if (res.ok && data.status === 'ok') {
        onLogin(data)
      } else {
        setError(data.error || '登录失败')
      }
    } catch (e) {
      setError('无法连接后端服务')
    }
    setLoading(false)
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
      fontFamily: 'Inter, system-ui, sans-serif'
    }}>
      <div style={{
        background: 'rgba(30, 41, 59, 0.8)',
        backdropFilter: 'blur(20px)',
        borderRadius: 24,
        padding: '48px',
        width: '100%',
        maxWidth: 420,
        boxShadow: '0 20px 40px rgba(0,0,0,0.3)',
        border: '1px solid rgba(255,255,255,0.08)'
      }}>
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <div style={{
            width: 64, height: 64, borderRadius: 20,
            background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 20px',
            boxShadow: '0 10px 20px rgba(59, 130, 246, 0.3)'
          }}>
            <Shield color="white" size={36} />
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: '#f1f5f9', marginBottom: 8 }}>管理员后台</h1>
          <p style={{ color: '#64748b', fontSize: 14 }}>光宸智能客服 系统管理控制台</p>
        </div>

        <form onSubmit={handleSubmit}>
          {error && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.1)', color: '#f87171', padding: '12px 16px',
              borderRadius: 12, fontSize: 13, marginBottom: 20, textAlign: 'center',
              fontWeight: 500, border: '1px solid rgba(239, 68, 68, 0.2)'
            }}>
              {error}
            </div>
          )}

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#94a3b8', marginBottom: 8 }}>管理员账号</label>
            <div style={{ position: 'relative' }}>
              <User size={18} color="#475569" style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)' }} />
              <input
                type="text"
                value={account}
                onChange={(e) => setAccount(e.target.value)}
                placeholder="输入管理员账号"
                style={{
                  width: '100%', padding: '14px 16px 14px 44px',
                  background: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 12, fontSize: 15, color: '#f1f5f9',
                  outline: 'none', transition: 'all 0.2s',
                  boxSizing: 'border-box'
                }}
                onFocus={(e) => { e.target.style.borderColor = '#3b82f6'; e.target.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.15)' }}
                onBlur={(e) => { e.target.style.borderColor = 'rgba(255,255,255,0.1)'; e.target.style.boxShadow = 'none' }}
              />
            </div>
          </div>

          <div style={{ marginBottom: 32 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#94a3b8', marginBottom: 8 }}>密码</label>
            <div style={{ position: 'relative' }}>
              <Lock size={18} color="#475569" style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)' }} />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="输入管理员密码"
                style={{
                  width: '100%', padding: '14px 16px 14px 44px',
                  background: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 12, fontSize: 15, color: '#f1f5f9',
                  outline: 'none', transition: 'all 0.2s',
                  boxSizing: 'border-box'
                }}
                onFocus={(e) => { e.target.style.borderColor = '#3b82f6'; e.target.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.15)' }}
                onBlur={(e) => { e.target.style.borderColor = 'rgba(255,255,255,0.1)'; e.target.style.boxShadow = 'none' }}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: '100%', padding: '14px',
              background: loading ? '#475569' : '#3b82f6',
              color: 'white', border: 'none', borderRadius: 12,
              fontSize: 16, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: 8, transition: 'all 0.2s',
              boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)'
            }}
          >
            {loading ? '正在登录...' : '登录管理后台'}
            {!loading && <ArrowRight size={18} />}
          </button>
        </form>

        {onBack && (
          <div style={{ textAlign: 'center', marginTop: 24 }}>
            <button
              type="button"
              onClick={onBack}
              style={{
                background: 'none', border: 'none', color: '#64748b',
                fontSize: 13, cursor: 'pointer', display: 'inline-flex',
                alignItems: 'center', gap: 6,
              }}
              onMouseOver={(e) => e.currentTarget.style.color = '#94a3b8'}
              onMouseOut={(e) => e.currentTarget.style.color = '#64748b'}
            >
              <ArrowLeft size={14} />
              返回商家登录
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
