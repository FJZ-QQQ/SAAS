import { useState, useEffect, useRef } from 'react'
import { Send, Search, Inbox, MessageSquare, Bot, User, Store, ChevronDown } from 'lucide-react'

const formatStoreName = (id) => `${id}号店铺`

export default function Messages({ merchantData }) {
  const [selectedChat, setSelectedChat] = useState(null)
  const [chats, setChats] = useState([])
  const [loading, setLoading] = useState(true)
  const [inputText, setInputText] = useState('')
  const [sending, setSending] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [selectedStore, setSelectedStore] = useState('all') // 'all' or slot_id
  const [storeList, setStoreList] = useState([])
  const messagesEndRef = useRef(null)
  const currentMid = merchantData?.merchant_id ? String(merchantData.merchant_id) : ''

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

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  // Fetch store list from /status
  useEffect(() => {
    const fetchStores = () => {
      const qs = currentMid ? `?owner_merchant_id=${currentMid}` : ''
      fetch(`http://localhost:8100/status${qs}`, { headers: getAuthHeaders() })
        .then(r => r.json())
        .then(data => {
          const stores = Object.entries(data)
            .map(([id, info]) => ({
              id,
              name: formatStoreName(id),
              status: info.status,
              msgCount: info.total_messages || 0,
            }))
          setStoreList(stores)
        })
        .catch(() => {})
    }
    fetchStores()
    const timer = setInterval(fetchStores, 5000)
    return () => clearInterval(timer)
  }, [currentMid])

  useEffect(() => {
    const fetchMessages = () => {
      fetch(`http://localhost:8100/api/messages?merchant_id=${currentMid || 0}`, { headers: getAuthHeaders() })
        .then(r => r.json())
        .then(data => {
          const grouped = {}
          data.forEach(msg => {
            const accountId = String(msg.account_id || msg.account?.replace(/[^0-9]/g, '') || '')
            const key = `${accountId}_${msg.sender}`
            if (!grouped[key]) {
              grouped[key] = {
                id: key,
                name: msg.sender,
                account: msg.account,
                accountId,
                messages: [],
                lastTime: msg.time,
                preview: msg.text,
              }
            }
            grouped[key].messages.push(msg)
            grouped[key].lastTime = msg.time
            grouped[key].preview = msg.text
          })
          const chatList = Object.values(grouped).sort((a, b) => b.lastTime.localeCompare(a.lastTime))
          setChats(chatList)
          setLoading(false)
        })
        .catch(e => { console.error(e); setLoading(false) })
    }
    fetchMessages()
    const timer = setInterval(fetchMessages, 3000)
    return () => clearInterval(timer)
  }, [currentMid])

  useEffect(() => { scrollToBottom() }, [chats, selectedChat])

  const handleSend = async () => {
    if (!inputText.trim() || !selectedChat) return
    const current = chats.find(c => c.id === selectedChat)
    if (!current) return
    setSending(true)
    try {
      const mid = Number(current.accountId || 0)
      const res = await fetch(`http://localhost:8100/test_reply/${mid}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({ sender: current.name, text: inputText })
      })
      const result = await res.json()
      if (result.error) {
        alert('发送失败: ' + result.error)
      } else {
        const newMsg = {
          id: Date.now(), sender: '我', text: inputText,
          time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
          account: current.account, is_ai: true
        }
        setChats(prev => prev.map(chat => {
          if (chat.id === selectedChat) {
            return { ...chat, messages: [...chat.messages, newMsg], preview: inputText, lastTime: newMsg.time }
          }
          return chat
        }))
        setInputText('')
      }
    } catch (error) {
      alert('网络错误，无法发送')
    } finally { setSending(false) }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const currentChat = chats.find(c => c.id === selectedChat)
  const messages = currentChat?.messages || []

  // Filter by store and search
  const filteredChats = chats.filter(c => {
    if (selectedStore !== 'all' && c.accountId !== selectedStore) return false
    if (searchText && !c.name.includes(searchText) && !c.preview.includes(searchText)) return false
    return true
  })

  // Count messages per store for badge
  const storeMsgCount = {}
  chats.forEach(c => {
    storeMsgCount[c.accountId] = (storeMsgCount[c.accountId] || 0) + c.messages.length
  })

  const totalChats = chats.length
  const storeColors = ['#f97316', '#3b82f6', '#10b981', '#8b5cf6', '#ec4899']
  const getStoreName = (id) => storeList.find(s => s.id === String(id))?.name || formatStoreName(id)

  return (
    <>
      <header className="page-header">
        <h1 className="page-title">消息监控</h1>
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          🤖 AI 自动回复中 · {totalChats} 个对话
        </span>
      </header>

      <div style={{
        display: 'flex', height: 'calc(100vh - 120px)',
        background: 'var(--bg-card)', borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border-color)', overflow: 'hidden',
        boxShadow: 'var(--shadow-card)',
      }}>
        {/* 左侧会话列表 */}
        <div style={{
          width: 300, minWidth: 300, borderRight: '1px solid var(--border-color)',
          display: 'flex', flexDirection: 'column', background: 'var(--bg-card)',
        }}>
          {/* 店铺切换标签 */}
          <div style={{
            padding: '10px 12px', borderBottom: '1px solid var(--border-color)',
            display: 'flex', gap: 6, overflowX: 'auto', flexShrink: 0,
          }}>
            <button
              onClick={() => { setSelectedStore('all'); setSelectedChat(null) }}
              style={{
                padding: '5px 12px', borderRadius: 20, border: 'none', cursor: 'pointer',
                fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', flexShrink: 0,
                background: selectedStore === 'all'
                  ? 'var(--accent-orange)' : 'var(--bg-input)',
                color: selectedStore === 'all' ? 'white' : 'var(--text-secondary)',
                transition: 'all 0.2s',
              }}
            >
              全部 ({totalChats})
            </button>
            {storeList.map((store, idx) => {
              const count = storeMsgCount[store.id] || 0
              const isActive = selectedStore === store.id
              const color = storeColors[idx % storeColors.length]
              return (
                <button
                  key={store.id}
                  onClick={() => { setSelectedStore(store.id); setSelectedChat(null) }}
                  style={{
                    padding: '5px 12px', borderRadius: 20, border: 'none', cursor: 'pointer',
                    fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', flexShrink: 0,
                    background: isActive ? color : 'var(--bg-input)',
                    color: isActive ? 'white' : 'var(--text-secondary)',
                    transition: 'all 0.2s',
                    display: 'flex', alignItems: 'center', gap: 4,
                  }}
                >
                  <span style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: store.status === 'running' ? '#22c55e' : '#94a3b8',
                    flexShrink: 0,
                  }} />
                  {store.name}
                  {count > 0 && (
                    <span style={{
                      fontSize: 10, padding: '0 5px', borderRadius: 10,
                      background: isActive ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.08)',
                    }}>{count}</span>
                  )}
                </button>
              )
            })}
          </div>

          {/* 搜索框 */}
          <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-color)' }}>
            <div style={{ position: 'relative' }}>
              <Search size={15} style={{
                position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)',
                color: 'var(--text-muted)'
              }} />
              <input
                placeholder="搜索对话..."
                value={searchText}
                onChange={e => setSearchText(e.target.value)}
                style={{
                  width: '100%', padding: '8px 12px 8px 36px',
                  border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)',
                  background: 'var(--bg-input)', fontSize: 12, outline: 'none',
                  color: 'var(--text-primary)', boxSizing: 'border-box',
                }}
              />
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto' }}>
            {loading && chats.length === 0 ? (
              <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
                加载中...
              </div>
            ) : filteredChats.length === 0 ? (
              <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
                <Inbox size={36} style={{ marginBottom: 12, opacity: 0.3 }} />
                <div style={{ fontSize: 14, fontWeight: 600 }}>
                  {selectedStore !== 'all' ? '该店铺暂无对话' : '暂无对话'}
                </div>
                <div style={{ fontSize: 12, marginTop: 6 }}>
                  启动 RPA 后，收到的私信会显示在这里
                </div>
              </div>
            ) : filteredChats.map(chat => {
              const storeIdx = storeList.findIndex(s => s.id === chat.accountId)
              const dotColor = storeIdx >= 0 ? storeColors[storeIdx % storeColors.length] : 'var(--accent-orange)'
              return (
                <div
                  key={chat.id}
                  onClick={() => setSelectedChat(chat.id)}
                  style={{
                    padding: '12px 14px', cursor: 'pointer',
                    borderBottom: '1px solid var(--border-color)',
                    background: selectedChat === chat.id ? 'var(--accent-orange-glow)' : 'transparent',
                    borderLeft: selectedChat === chat.id ? '3px solid var(--accent-orange)' : '3px solid transparent',
                    transition: 'var(--transition-fast)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 3 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{
                        fontSize: 13, fontWeight: 600,
                        color: selectedChat === chat.id ? 'var(--accent-orange)' : 'var(--text-primary)',
                      }}>{chat.name}</span>
                      {/* 店铺标签 */}
                      <span style={{
                        fontSize: 9, padding: '1px 6px', borderRadius: 10,
                        background: dotColor + '18', color: dotColor, fontWeight: 600,
                      }}>
                        {getStoreName(chat.accountId)}
                      </span>
                    </div>
                    <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{chat.lastTime}</span>
                  </div>
                  <div style={{
                    fontSize: 11, color: 'var(--text-muted)',
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>{chat.preview}</div>
                </div>
              )
            })}
          </div>
        </div>

        {/* 右侧聊天区域 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--bg-primary)' }}>
          {currentChat ? (
            <>
              {/* 聊天头部 */}
              <div style={{
                padding: '14px 20px', borderBottom: '1px solid var(--border-color)',
                background: 'var(--bg-card)', display: 'flex', alignItems: 'center', gap: 10,
              }}>
                <div style={{
                  width: 36, height: 36, borderRadius: '50%',
                  background: 'linear-gradient(135deg, var(--accent-orange), #f59e0b)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: '#fff', fontSize: 14, fontWeight: 700,
                }}>{currentChat.name[0]}</div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>{currentChat.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{getStoreName(currentChat.accountId)}</div>
                </div>
              </div>

              {/* 消息列表 */}
              <div style={{ flex: 1, padding: 20, overflowY: 'auto' }}>
                {messages.map((msg, idx) => (
                  <div key={idx} style={{
                    display: 'flex', justifyContent: msg.is_ai ? 'flex-end' : 'flex-start',
                    marginBottom: 12,
                  }}>
                    {!msg.is_ai && (
                      <div style={{
                        width: 32, height: 32, borderRadius: '50%', marginRight: 10,
                        background: 'var(--bg-card)', border: '1px solid var(--border-color)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>
                        <User size={16} style={{ color: 'var(--text-muted)' }} />
                      </div>
                    )}
                    <div style={{
                      maxWidth: '60%', padding: '10px 14px',
                      borderRadius: msg.is_ai ? '14px 4px 14px 14px' : '4px 14px 14px 14px',
                      background: msg.is_ai ? 'var(--accent-orange)' : 'var(--bg-card)',
                      color: msg.is_ai ? '#fff' : 'var(--text-primary)',
                      fontSize: 13, lineHeight: 1.6,
                      boxShadow: msg.is_ai ? 'none' : 'var(--shadow-card)',
                      border: msg.is_ai ? 'none' : '1px solid var(--border-color)',
                    }}>
                      {msg.text}
                      <div style={{
                        fontSize: 10, marginTop: 4, textAlign: 'right',
                        opacity: 0.6,
                      }}>{msg.time}</div>
                    </div>
                    {msg.is_ai && (
                      <div style={{
                        width: 32, height: 32, borderRadius: '50%', marginLeft: 10,
                        background: 'linear-gradient(135deg, var(--accent-orange), #f59e0b)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>
                        <Bot size={16} style={{ color: '#fff' }} />
                      </div>
                    )}
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>

              {/* 输入区域 */}
              <div style={{
                padding: '12px 16px', borderTop: '1px solid var(--border-color)',
                background: 'var(--bg-card)', display: 'flex', gap: 10, alignItems: 'flex-end',
              }}>
                <textarea
                  placeholder="输入回复内容（Enter 发送，Shift+Enter 换行）..."
                  value={inputText}
                  onChange={e => setInputText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={2}
                  style={{
                    flex: 1, padding: '10px 14px', border: '1px solid var(--border-color)',
                    borderRadius: 'var(--radius-md)', background: 'var(--bg-input)',
                    fontSize: 13, resize: 'none', outline: 'none',
                    color: 'var(--text-primary)', fontFamily: 'inherit',
                  }}
                />
                <button
                  onClick={handleSend}
                  disabled={sending || !inputText.trim()}
                  style={{
                    padding: '10px 20px', borderRadius: 'var(--radius-md)',
                    background: inputText.trim() ? 'var(--accent-orange)' : 'var(--bg-input)',
                    color: inputText.trim() ? '#fff' : 'var(--text-muted)',
                    border: 'none', cursor: inputText.trim() ? 'pointer' : 'default',
                    fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6,
                    transition: 'var(--transition-fast)',
                  }}
                >
                  <Send size={14} />
                  {sending ? '发送中' : '发送'}
                </button>
              </div>
            </>
          ) : (
            <div style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <div style={{ textAlign: 'center' }}>
                <MessageSquare size={48} style={{ color: 'var(--accent-orange)', opacity: 0.3, marginBottom: 16 }} />
                <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
                  请在左侧选择一个会话
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                  选择后即可查看聊天记录并手动回复
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
