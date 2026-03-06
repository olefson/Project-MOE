import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

const API_BASE = 'http://localhost:8000'
const SESSION_STORAGE_KEY = 'moe_session_id'

function App() {
  const [message, setMessage] = useState('')
  const [reply, setReply] = useState('')
  const [conversationHistory, setConversationHistory] = useState([])
  const [reasoningUsed, setReasoningUsed] = useState(null)
  const [showWhy, setShowWhy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [recordingBlob, setRecordingBlob] = useState(null)
  const [isRecording, setIsRecording] = useState(false)
  const [recordingError, setRecordingError] = useState(null)
  const mediaRecorderRef = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])

  useEffect(() => {
    const stored = localStorage.getItem(SESSION_STORAGE_KEY)
    if (stored) setSessionId(stored)
  }, [])

  async function handleSend() {
    const text = message.trim()
    if (!text || loading) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: sessionId || undefined,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        const d = data.detail
        const errMsg = typeof d === 'string' ? d : Array.isArray(d) && d[0] ? (d[0].msg || d[0].message || String(d[0])) : res.statusText || 'Request failed'
        setError(errMsg)
        return
      }
      const assistantReply = data.reply ?? ''
      setReply(assistantReply)
      setReasoningUsed(data.reasoning_used ?? null)
      setShowWhy(false)
      setConversationHistory((prev) => [...prev, { role: 'user', content: text }, { role: 'assistant', content: assistantReply }])
      if (data.session_id) {
        setSessionId(data.session_id)
        localStorage.setItem(SESSION_STORAGE_KEY, data.session_id)
      }
      setMessage('')
    } catch (err) {
      setError(err.message || 'Network error')
    } finally {
      setLoading(false)
    }
  }

  async function toggleRecord() {
    if (isRecording) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }
      streamRef.current?.getTracks?.().forEach((t) => t.stop())
      return
    }
    setRecordingError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const recorder = new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      chunksRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data.size) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        setRecordingBlob(blob)
        setIsRecording(false)
      }
      recorder.start()
      setIsRecording(true)
    } catch (err) {
      setRecordingError(err.message || 'Microphone access denied')
      setIsRecording(false)
    }
  }

  async function handleSubmitVoice() {
    if (!recordingBlob || loading) return
    setLoading(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', recordingBlob, 'recording.webm')
      if (sessionId) form.append('session_id', sessionId)
      const res = await fetch(`${API_BASE}/audio`, {
        method: 'POST',
        body: form,
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        const d = data.detail
        const errMsg = typeof d === 'string' ? d : Array.isArray(d) && d[0] ? (d[0].msg || d[0].message || String(d[0])) : res.statusText || 'Request failed'
        setError(errMsg)
        return
      }
      const assistantReply = data.reply ?? ''
      setReply(assistantReply)
      setReasoningUsed(data.reasoning_used ?? null)
      setShowWhy(false)
      setConversationHistory((prev) => [...prev, { role: 'user', content: data.transcript ?? '(voice)' }, { role: 'assistant', content: assistantReply }])
      if (data.session_id) {
        setSessionId(data.session_id)
        localStorage.setItem(SESSION_STORAGE_KEY, data.session_id)
      }
      setRecordingBlob(null)
    } catch (err) {
      setError(err.message || 'Network error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-svh flex flex-col items-center justify-center p-4 bg-background">
      <div className="w-full max-w-2xl space-y-4">
        <h1 className="text-2xl font-semibold text-foreground">PMO</h1>
        <Card className="flex flex-col max-h-[60vh]">
          <CardHeader>
            <CardTitle>Conversation</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 overflow-y-auto min-h-[160px] space-y-4">
            {conversationHistory.length === 0 && !reply ? (
              <p className="text-muted-foreground">
                {loading ? 'Thinking…' : 'Send a message to get a reply.'}
              </p>
            ) : (
              <>
                {conversationHistory.map((entry, i) => (
                  <div key={i} className={entry.role === 'user' ? 'text-right' : ''}>
                    <p className="text-xs font-medium text-muted-foreground mb-1">
                      {entry.role === 'user' ? 'You' : 'PMO'}
                    </p>
                    <p className={`text-sm whitespace-pre-wrap ${entry.role === 'user' ? 'text-foreground' : 'text-foreground'}`}>
                      {entry.content}
                    </p>
                  </div>
                ))}
                {loading && (
                  <p className="text-muted-foreground text-sm">Thinking…</p>
                )}
                {reply && (
                  <div className="pt-2">
                    {reasoningUsed && (
                      <>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setShowWhy((v) => !v)}
                          className="text-muted-foreground"
                        >
                          {showWhy ? 'Hide' : 'Why did you say that?'}
                        </Button>
                        {showWhy && (
                          <div className="mt-2 p-3 rounded-md bg-muted text-sm space-y-2">
                            {reasoningUsed.memories?.length > 0 && (
                              <div>
                                <p className="font-medium text-foreground">Memories used</p>
                                <ul className="list-disc list-inside text-muted-foreground">
                                  {(reasoningUsed.memories || []).map((m, i) => (
                                    <li key={i}>{m.content}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {reasoningUsed.tool_calls?.length > 0 && (
                              <div>
                                <p className="font-medium text-foreground">Tools used</p>
                                <ul className="list-disc list-inside text-muted-foreground">
                                  {(reasoningUsed.tool_calls || []).map((t, i) => (
                                    <li key={i}>
                                      {t.name}({typeof t.arguments === 'object' ? JSON.stringify(t.arguments) : t.arguments})
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {(!reasoningUsed.memories?.length && !reasoningUsed.tool_calls?.length) && (
                              <p className="text-muted-foreground">No memories or tools used for this reply.</p>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
        {error && (
          <p className="text-destructive text-sm" role="alert">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <Input
            placeholder="Type a message…"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            disabled={loading}
            className="flex-1"
          />
          <Button
            onClick={handleSend}
            disabled={loading || !message.trim()}
          >
            Send
          </Button>
        </div>
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Voice</p>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant={isRecording ? 'destructive' : 'outline'}
              onClick={toggleRecord}
              disabled={loading}
            >
              {isRecording ? 'Stop' : 'Record'}
            </Button>
            <Button
              onClick={handleSubmitVoice}
              disabled={loading || !recordingBlob}
            >
              Submit
            </Button>
            <span className="text-sm text-muted-foreground">
              {isRecording ? 'Recording…' : recordingBlob ? 'Recorded' : 'No recording'}
            </span>
          </div>
          {recordingError && (
            <p className="text-destructive text-sm" role="alert">
              {recordingError}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
