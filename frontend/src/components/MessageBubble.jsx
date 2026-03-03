import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Bot, User, AlertTriangle } from 'lucide-react'

function formatTime(date) {
  if (!date) return ''
  const d = date instanceof Date ? date : new Date(date)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function MessageBubble({ message }) {
  const { role, content, model, iterations, timestamp } = message

  const isUser      = role === 'user'
  const isAssistant = role === 'assistant'
  const isError     = role === 'error'

  const avatarClass = isUser
    ? 'avatar-user'
    : isError
    ? 'avatar-error'
    : 'avatar-assistant'

  const bubbleClass = isUser
    ? 'bubble-user'
    : isError
    ? 'bubble-error'
    : 'bubble-assistant'

  const AvatarIcon = isUser ? User : isError ? AlertTriangle : Bot

  return (
    <div className={`msg-wrapper ${isUser ? 'user-wrapper' : ''}`}>
      <div className={`msg-avatar ${avatarClass}`}>
        <AvatarIcon size={16} />
      </div>

      <div className="msg-body" style={isUser ? { alignItems: 'flex-end' } : {}}>
        <div className={`msg-bubble ${bubbleClass}`}>
          {isUser ? (
            <span style={{ whiteSpace: 'pre-wrap' }}>{content}</span>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
          )}
        </div>

        <div className="msg-meta" style={isUser ? { flexDirection: 'row-reverse' } : {}}>
          <span className="msg-time">{formatTime(timestamp)}</span>
          {isAssistant && model && (
            <span className="msg-model-badge">{model}</span>
          )}
          {isAssistant && iterations !== undefined && (
            <span
              style={{
                fontSize: '10px',
                color: 'var(--text-muted)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {iterations} iteration{iterations !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
