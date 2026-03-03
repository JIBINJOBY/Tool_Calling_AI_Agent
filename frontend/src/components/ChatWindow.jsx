import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'
import { Send, Trash2, CornerDownLeft } from 'lucide-react'

export default function ChatWindow({ messages, loading, onSend, onClear, inputRef }) {
  const [input, setInput] = useState('')
  const bottomRef = useRef(null)

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSend = () => {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    onSend(q)
  }

  const handleInput = (e) => {
    setInput(e.target.value)
    // Auto-resize textarea
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'
  }

  return (
    <div className="chat-window">
      {/* Messages */}
      <div className="messages-list">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Typing indicator */}
        {loading && (
          <div className="msg-wrapper">
            <div className="msg-avatar avatar-assistant">🤖</div>
            <div className="msg-body">
              <div className="typing-indicator">
                <div className="typing-dot" />
                <div className="typing-dot" />
                <div className="typing-dot" />
              </div>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)', paddingLeft: '4px' }}>
                Calling tools…
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="chat-input-area">
        <div className="chat-input-row">
          <textarea
            ref={inputRef}
            className="chat-textarea"
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your pipeline, forecasts, sector performance…"
            rows={1}
            disabled={loading}
          />
          <button
            className="btn-send"
            onClick={handleSend}
            disabled={!input.trim() || loading}
            title="Send (Enter)"
          >
            <Send size={16} />
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '8px' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <CornerDownLeft size={11} /> Enter to send · Shift+Enter for newline
          </span>
          <button className="btn-clear" onClick={onClear}>
            <Trash2 size={11} style={{ display: 'inline', marginRight: '4px' }} />
            Clear chat
          </button>
        </div>
      </div>
    </div>
  )
}
