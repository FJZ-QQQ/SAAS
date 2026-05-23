import { useState, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Users, MessageSquare,
  Target, User, LogOut, Bot
} from 'lucide-react'

const navItems = [
  { path: '/', icon: LayoutDashboard, label: '首页', section: '概览' },
  { path: '/accounts', icon: Users, label: '账号管理', section: '管理' },
  { path: '/messages', icon: MessageSquare, label: '消息监控', section: '管理' },
  { path: '/leads', icon: Target, label: '我的客资', section: '管理' },
  { path: '/scripts', icon: Bot, label: 'AI 智能体', section: '配置' },
  { path: '/my-account', icon: User, label: '我的账户', section: '配置' },
]

export default function Sidebar({ merchantData, onLogout }) {
  const location = useLocation()
  const [balance, setBalance] = useState(merchantData?.balance ?? 0)

  // 实时刷新余额
  useEffect(() => {
    const fetchBalance = async () => {
      try {
        const res = await fetch(`http://localhost:8100/api/account?merchant_id=${merchantData?.merchant_id || 0}`)
        const data = await res.json()
        if (data.balance !== undefined) setBalance(data.balance)
      } catch (e) {
        // ignore
      }
    }
    fetchBalance()
    const timer = setInterval(fetchBalance, 8000)
    return () => clearInterval(timer)
  }, [merchantData])

  // Group items by section
  const sections = {}
  navItems.forEach(item => {
    if (!sections[item.section]) sections[item.section] = []
    sections[item.section].push(item)
  })

  const phone = merchantData?.phone || '未知'
  const displayPhone = phone.length === 11
    ? phone.slice(0, 3) + '****' + phone.slice(7)
    : phone

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-icon">💡</div>
        <span className="logo-text">光宸智能客服</span>
      </div>

      <nav className="sidebar-nav">
        {Object.entries(sections).map(([section, items]) => (
          <div key={section}>
            <div className="sidebar-section-label">{section}</div>
            {items.map(item => {
              const Icon = item.icon
              const isActive = location.pathname === item.path
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={`nav-item ${isActive ? 'active' : ''}`}
                >
                  <Icon className="nav-icon" size={20} />
                  <span>{item.label}</span>
                </NavLink>
              )
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        {/* 余额显示 — 实时刷新 */}
        <div style={{
          padding: '12px 14px', marginBottom: 8,
          background: balance <= 0 ? 'rgba(220, 53, 69, 0.12)' 
                    : balance <= 10 ? 'rgba(255, 107, 53, 0.12)'
                    : balance <= 50 ? 'rgba(255, 193, 7, 0.08)'
                    : 'rgba(14, 167, 112, 0.08)',
          borderRadius: 10, textAlign: 'center',
          border: balance <= 10 ? '1px solid rgba(220, 53, 69, 0.3)' : 'none',
          animation: balance <= 0 ? 'pulse-warning 2s ease-in-out infinite' : 'none',
        }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>账户余额</div>
          <div style={{
            fontSize: 22, fontWeight: 700,
            color: balance <= 0 ? 'var(--accent-red)' 
                 : balance <= 10 ? '#ff6b35'
                 : balance <= 50 ? '#e6a700'
                 : 'var(--accent-green)',
          }}>
            ¥{Number(balance).toFixed(2)}
          </div>
          {balance <= 0 && (
            <div style={{ fontSize: 10, color: 'var(--accent-red)', marginTop: 4, fontWeight: 600 }}>
              🚫 余额不足，AI已暂停回复
              <div style={{ marginTop: 4, fontSize: 9, color: 'var(--text-muted)' }}>
                请联系管理员充值以恢复服务
              </div>
            </div>
          )}
          {balance > 0 && balance <= 10 && (
            <div style={{ fontSize: 10, color: '#ff6b35', marginTop: 4, fontWeight: 600 }}>
              ⚠️ 余额即将用完，请尽快充值！
              <div style={{ marginTop: 4, fontSize: 9, color: 'var(--text-muted)' }}>
                剩余约 {Math.floor(balance)} 条客资额度
              </div>
            </div>
          )}
          {balance > 10 && balance <= 50 && (
            <div style={{ fontSize: 10, color: '#e6a700', marginTop: 4, fontWeight: 600 }}>
              💡 余额偏低，建议及时充值
            </div>
          )}
        </div>

        <div className="sidebar-user">
          <div className="user-avatar">
            {phone ? phone.slice(-2) : '橙'}
          </div>
          <div className="user-info">
            <div className="user-name">{displayPhone}</div>
            <div className="user-plan">● 商户账号</div>
          </div>
        </div>
        
        <button 
          onClick={onLogout} 
          style={{
            width: '100%', padding: '10px', marginTop: '12px',
            background: 'var(--bg-input)', border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-md)', color: 'var(--text-secondary)',
            fontSize: '13px', fontWeight: '600', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
            transition: 'all 0.2s'
          }}
          onMouseOver={(e) => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.color = 'var(--accent-orange)'; }}
          onMouseOut={(e) => { e.currentTarget.style.background = 'var(--bg-input)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
        >
          <LogOut size={16} /> 退出登录 / 切换账号
        </button>
      </div>
    </aside>
  )
}
