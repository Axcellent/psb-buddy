import { useEffect, useMemo, useRef, useState } from "react"
import { Document, Page, pdfjs } from "react-pdf"
import {
  MessageCircle,
  Search,
  ChevronLeft,
  ChevronRight,
  Minus,
  Plus,
  X,
  FileText,
  Send,
  Copy,
  ThumbsUp,
  ThumbsDown,
  Check,
  Command,
  ArrowUpRight,
} from "lucide-react"

import "react-pdf/dist/Page/AnnotationLayer.css"
import "react-pdf/dist/Page/TextLayer.css"

import { api, apiUrl } from "./api"
import TextReader from "./TextReader"

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString()

const LogoMark = ({ small = false }) => (
  <img
    src="/psb.svg"
    alt="ПСБ"
    className={`logo-mark${small ? " logo-mark-small" : ""}`}
    width={small ? 24 : 32}
    height={small ? 24 : 32}
  />
)

function MessageBubble({ message, onSelectSource, isWelcome = false }) {
  const [copied, setCopied] = useState(false)
  const [reaction, setReaction] = useState("")
  const isAssistant = message.role === "assistant"

  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(message.text)
    } catch {}
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  return (
    <article
      className={`message-row ${isAssistant ? "message-assistant" : "message-user"}`}
    >
      {isAssistant && (
        <div className="avatar assistant-avatar">
          <LogoMark small />
        </div>
      )}
      <div className="message-content">
        <div className="message-meta">
          <strong>{isAssistant ? "PSB AI" : "Вы"}</strong>
          <span>{message.time}</span>
          {isAssistant && (
            <button
              className="source-count"
              onClick={() =>
                message.sources?.[0] && onSelectSource(message.sources[0])
              }
            >
              <FileText size={13} />
              Источники - {message.sources?.length ?? 0}
            </button>
          )}
        </div>
        <div
          className={`bubble ${isAssistant ? "assistant-bubble" : "user-bubble"}`}
        >
          {isAssistant && (
            <span className="answer-status">
              <Check size={12} />
              ответ готов
            </span>
          )}
          <p>{message.text}</p>
          {isAssistant && message.sources?.length > 0 && (
            <div className="inline-sources">
              {message.sources.map((source, i) => (
                <button
                  key={`${source.id || source.title}-${i}`}
                  className="inline-source"
                  onClick={() => onSelectSource(source)}
                >
                  <FileText size={13} />
                  {source.title}
                  <ArrowUpRight size={12} />
                </button>
              ))}
            </div>
          )}
        </div>
        {isAssistant && !isWelcome && (
          <div className="message-actions" aria-label="Действия с ответом">
            <button onClick={copyText} title="Скопировать">
              <Copy size={14} />
              {copied && <span>Скопировано</span>}
            </button>
            <button
              className={reaction === "up" ? "selected" : ""}
              onClick={() => setReaction(reaction === "up" ? "" : "up")}
              title="Полезный ответ"
            >
              <ThumbsUp size={14} />
            </button>
            <button
              className={reaction === "down" ? "selected" : ""}
              onClick={() => setReaction(reaction === "down" ? "" : "down")}
              title="Неполезный ответ"
            >
              <ThumbsDown size={14} />
            </button>
          </div>
        )}
      </div>
      {!isAssistant && <div className="avatar user-avatar">ВЫ</div>}
    </article>
  )
}

function PdfReader({ source, onClose }) {
  const [numPages, setNumPages] = useState(0)
  const [pageNumber, setPageNumber] = useState(1)
  const [scale, setScale] = useState(1)
  const [containerWidth, setContainerWidth] = useState(600)
  const [pageError, setPageError] = useState(false)

  const bodyRef = useRef(null)
  const closeRef = useRef(null)

  useEffect(() => {
    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow

    document.body.style.overflow = "hidden"
    closeRef.current?.focus()

    const element = bodyRef.current

    const observer = new ResizeObserver(([entry]) => {
      setContainerWidth(Math.max(100, Math.floor(entry.contentRect.width)))
    })

    if (element) observer.observe(element)

    return () => {
      observer.disconnect()
      document.body.style.overflow = previousOverflow
      previousFocus?.focus?.()
    }
  }, [])

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: 0, left: 0 })
    setPageError(false)
  }, [pageNumber])

  const handleLoadSuccess = ({ numPages: count }) => {
    setNumPages(count)
    const requestedPage = Number(source.page)
    const initialPage = Number.isInteger(requestedPage) ? requestedPage : 1
    setPageNumber(Math.min(Math.max(initialPage, 1), count))
  }

  const handleKeyDown = (event) => {
    if (event.key === "Escape") {
      onClose()
      return
    }
    if (event.key !== "Tab") return

    const controls = Array.from(
      event.currentTarget.querySelectorAll(
        "button:not(:disabled), input:not(:disabled), a[href]",
      ),
    ).filter((element) => element.getClientRects().length > 0)

    const first = controls[0]
    const last = controls[controls.length - 1]

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first?.focus()
    }
  }

  const pageWidth = Math.min(containerWidth, 780)

  return (
    <div
      className="pdf-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <section
        className="pdf-reader"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pdf-reader-title"
        onKeyDown={handleKeyDown}
      >
        <header className="pdf-reader-header">
          <div className="pdf-reader-title">
            <span>Просмотр документа</span>
            <h2 id="pdf-reader-title">{source.title}</h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="icon-button"
            aria-label="Закрыть документ"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </header>
        <div className="pdf-toolbar">
          <div className="pdf-control-group">
            <button
              type="button"
              className="icon-button"
              aria-label="Предыдущая страница"
              disabled={!numPages || pageNumber <= 1}
              onClick={() => setPageNumber((prev) => prev - 1)}
            >
              <ChevronLeft size={18} />
            </button>
            <span className="pdf-page-label" aria-live="polite">
              {numPages ? `${pageNumber} / ${numPages}` : "- / -"}
            </span>
            <button
              type="button"
              className="icon-button"
              aria-label="Следующая страница"
              disabled={!numPages || pageNumber >= numPages}
              onClick={() => setPageNumber((prev) => prev + 1)}
            >
              <ChevronRight size={18} />
            </button>
          </div>
          <div className="pdf-control-group">
            <button
              type="button"
              className="icon-button"
              aria-label="Уменьшить масштаб"
              disabled={scale <= 0.5}
              onClick={() =>
                setScale((prev) =>
                  Math.max(0.5, Number((prev - 0.25).toFixed(2))),
                )
              }
            >
              <Minus size={17} />
            </button>
            <button
              type="button"
              className="pdf-zoom-reset"
              title="Сбросить масштаб"
              onClick={() => setScale(1)}
            >
              {Math.round(scale * 100)}%
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label="Увеличить масштаб"
              disabled={scale >= 2}
              onClick={() =>
                setScale((prev) =>
                  Math.min(2, Number((prev + 0.25).toFixed(2))),
                )
              }
            >
              <Plus size={17} />
            </button>
          </div>
        </div>
        <div className="pdf-reader-body" ref={bodyRef}>
          <Document
            file={apiUrl(source.pdfUrl)}
            onLoadSuccess={handleLoadSuccess}
            onLoadError={(error) => {
              setNumPages(0)
              console.error("Ошибка загрузки PDF:", error)
            }}
            loading={
              <p className="pdf-status" role="status">
                Загрузка документа…
              </p>
            }
            error={
              <div className="pdf-status" role="alert">
                <strong>Не удалось открыть PDF.</strong>
                <p>Проверьте адрес документа.</p>
              </div>
            }
            noData={<p className="pdf-status">Адрес документа не указан.</p>}
          >
            {numPages > 0 && (
              <Page
                key={pageNumber}
                pageNumber={pageNumber}
                width={pageWidth}
                scale={scale}
                renderTextLayer
                renderAnnotationLayer
                onRenderError={() => setPageError(true)}
                loading={
                  <p className="pdf-status" role="status">
                    Загрузка страницы…
                  </p>
                }
                error={
                  <p className="pdf-status" role="alert">
                    Не удалось отобразить страницу.
                  </p>
                }
              />
            )}
          </Document>
          {pageError && (
            <p className="pdf-status" role="alert">
              Ошибка отрисовки. Попробуйте открыть другую страницу.
            </p>
          )}
        </div>
        {source.quote && (
          <footer className="pdf-reader-quote">
            <strong>Фрагмент, использованный в ответе</strong>
            <blockquote>{source.quote}</blockquote>
          </footer>
        )}
      </section>
    </div>
  )
}

export default function App() {
  const [chats, setChats] = useState([])
  const [activeChat, setActiveChat] = useState(null)
  const [conversations, setConversations] = useState({})
  const [input, setInput] = useState("")
  const [search, setSearch] = useState("")
  const [selectedSource, setSelectedSource] = useState(null)
  const [sourcesOpen] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [readerSource, setReaderSource] = useState(null)
  const [isTyping, setIsTyping] = useState(false)
  const [bootError, setBootError] = useState("")
  const [messageError, setMessageError] = useState("")

  const inputRef = useRef(null)
  const scrollRef = useRef(null)

  const messages = useMemo(
    () => conversations[activeChat] ?? [],
    [conversations, activeChat],
  )

  const sources = useMemo(
    () => messages.flatMap((m) => m.sources ?? []),
    [messages],
  )

  const filteredChats = useMemo(() => {
    const q = search.trim().toLowerCase()
    return q ? chats.filter((c) => c.title.toLowerCase().includes(q)) : chats
  }, [chats, search])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const list = await api.listChats()
        if (cancelled) return
        setChats(list)
        if (list.length > 0) {
          setActiveChat(list[0].id)
        } else {
          const chat = await api.createChat("Новый диалог")
          if (cancelled) return
          setChats([chat])
          setActiveChat(chat.id)
        }
      } catch (e) {
        if (!cancelled) setBootError(e.message || String(e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!activeChat) return
    let cancelled = false
    ;(async () => {
      try {
        const list = await api.listMessages(activeChat)
        if (cancelled) return
        setConversations((prev) => ({ ...prev, [activeChat]: list }))
      } catch (e) {
        if (!cancelled) setMessageError(e.message || String(e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [activeChat])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" })
  }, [messages.length, isTyping])

  const createChat = async () => {
    try {
      setMessageError("")
      const chat = await api.createChat("Новый диалог")
      setChats((prev) => [chat, ...prev])
      setActiveChat(chat.id)
      setInput("")
      setSidebarOpen(false)
      window.setTimeout(() => inputRef.current?.focus(), 60)
    } catch (e) {
      setMessageError(e.message || String(e))
    }
  }

  const deleteChat = async (chatId) => {
    if (!window.confirm("Удалить этот диалог?")) return
    try {
      await api.deleteChat(chatId)
      setChats((prev) => {
        const next = prev.filter((c) => c.id !== chatId)
        if (activeChat === chatId) setActiveChat(next[0]?.id ?? null)
        return next
      })
    } catch (e) {
      setMessageError(e.message || String(e))
    }
  }

  const sendMessage = async (event) => {
    event?.preventDefault?.()
    const text = input.trim()
    if (!text || isTyping || !activeChat) return
    const chatId = activeChat
    setInput("")
    setMessageError("")
    setIsTyping(true)

    const nowTime = new Date().toLocaleTimeString("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
    })

    const optimistic = {
      id: `optimistic-${Date.now()}`,
      role: "user",
      time: nowTime,
      text,
      sources: [],
    }

    setConversations((prev) => ({
      ...prev,
      [chatId]: [...(prev[chatId] ?? []), optimistic],
    }))

    setChats((prev) =>
      prev.map((c) =>
        c.id === chatId && c.title === "Новый диалог"
          ? {
              ...c,
              title: text.length > 30 ? `${text.slice(0, 30)}…` : text,
              date: "сейчас",
            }
          : c,
      ),
    )

    try {
      const reply = await api.sendMessage(chatId, text)
      setConversations((prev) => ({
        ...prev,
        [chatId]: [...(prev[chatId] ?? []), reply],
      }))
    } catch (e) {
      setMessageError(e.message || String(e))
    } finally {
      setIsTyping(false)
    }
  }

  const activateChat = (id) => {
    setActiveChat(id)
    setSidebarOpen(false)
    setSelectedSource(null)
    setReaderSource(null)
    setMessageError("")
  }

  return (
    <main className="workspace">
      {bootError && (
        <div className="error-banner" role="alert">
          Ошибка загрузки: {bootError}
        </div>
      )}

      {sidebarOpen && (
        <button
          className="mobile-scrim"
          aria-label="Закрыть меню"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside className={`sidebar panel ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand-lockup">
          <LogoMark />
          <div>
            <strong>PSB</strong>
            <span>AI ASSISTANT</span>
          </div>
          <button
            className="icon-button mobile-close"
            aria-label="Закрыть меню"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={18} />
          </button>
        </div>

        <button className="new-chat-button" onClick={createChat}>
          <Plus size={18} strokeWidth={2.2} />
          <span>Новый чат</span>
          <kbd>
            <Command size={10} /> K
          </kbd>
        </button>

        <div className="history-heading">
          <span>История диалогов</span>
          <span className="count-pill">{chats.length}</span>
        </div>

        <label className="chat-search">
          <Search size={14} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Найти диалог"
          />
        </label>

        <nav className="chat-list" aria-label="История диалогов">
          {filteredChats.map((chat) => (
            <div key={chat.id} className="chat-item-row">
              <button
                className={`chat-item ${activeChat === chat.id ? "active" : ""}`}
                onClick={() => activateChat(chat.id)}
              >
                <MessageCircle size={16} />
                <span className="chat-title">{chat.title}</span>
                <time>{chat.date}</time>
              </button>
              <button
                className="chat-delete"
                title="Удалить чат"
                aria-label="Удалить чат"
                onClick={(e) => {
                  e.stopPropagation()
                  deleteChat(chat.id)
                }}
              >
                <X size={13} />
              </button>
            </div>
          ))}
          {filteredChats.length === 0 && (
            <p className="empty-search">Диалоги не найдены</p>
          )}
        </nav>
      </aside>

      <section className="main-column">
        <section className="chat-panel panel">
          {messageError && (
            <div className="error-banner" role="alert">
              {messageError}
            </div>
          )}

          <div className="conversation" ref={scrollRef}>
            {messages.map((message, index) => (
              <MessageBubble
                key={message.id}
                message={message}
                isWelcome={index === 0 && message.role === "assistant"}
                onSelectSource={setSelectedSource}
              />
            ))}
            {isTyping && (
              <div className="typing-row">
                <div className="avatar assistant-avatar">
                  <LogoMark small />
                </div>
                <div className="typing-bubble">
                  <span />
                  <span />
                  <span />
                  <small>Ассистент готовит ответ</small>
                </div>
              </div>
            )}
          </div>

          <div className="composer-area">
            {messages.length <= 1 && (
              <div className="suggestions">
                <span>Попробуйте спросить</span>
                <button
                  onClick={() =>
                    setInput("Какие документы нужны для оформления отпуска?")
                  }
                >
                  Оформление отпуска
                </button>
                <button
                  onClick={() => setInput("На что обратить внимание в договоре?")}
                >
                  Проверка договора
                </button>
              </div>
            )}

            <form className="composer" onSubmit={sendMessage}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    sendMessage()
                  }
                }}
                placeholder="Задайте вопрос по документам..."
                rows={1}
              />
              <button
                className={`send-button ${input.trim() ? "ready" : ""}`}
                type="submit"
                disabled={!input.trim() || isTyping}
                aria-label="Отправить сообщение"
              >
                <Send size={16} />
              </button>
            </form>
          </div>
        </section>
      </section>

      {sourcesOpen && (
        <aside className="sources-panel panel">
          <div className="sources-heading">
            <div>
              <h2>Источники ответа</h2>
            </div>
            <span className="source-total">
              {String(sources.length).padStart(2, "0")}
            </span>
          </div>

          {selectedSource ? (
            <div className="source-detail">
              <button
                className="source-back"
                onClick={() => setSelectedSource(null)}
              >
                Все источники
              </button>
              <div className="source-file-icon">
                <FileText size={23} />
              </div>
              <span className="source-type">Источник ответа</span>
              <h3>{selectedSource.title}</h3>
              <div className="source-detail-row">
                <span>Раздел</span>
                <strong>{selectedSource.section || "—"}</strong>
              </div>
              <div className="source-detail-row">
                <span>Расположение</span>
                <strong>
                  {selectedSource.page ??
                    selectedSource.location ??
                    "—"}
                </strong>
              </div>
              <button
                type="button"
                className="open-document"
                disabled={!selectedSource.pdfUrl}
                onClick={() => setReaderSource(selectedSource)}
              >
                Открыть документ
                <ArrowUpRight size={14} />
              </button>
            </div>
          ) : sources.length ? (
            <div className="source-list">
              {sources.map((source, index) => (
                <button
                  key={`${source.id || source.title}-${index}`}
                  className="source-card"
                  onClick={() => setSelectedSource(source)}
                >
                  <div className="source-card-icon">
                    <FileText size={17} />
                  </div>
                  <div>
                    <strong>{source.title}</strong>
                    <span>
                      {source.section || "—"}
                      {source.page ? ` · ${source.page}` : ""}
                    </span>
                  </div>
                  <ArrowUpRight size={14} />
                </button>
              ))}
            </div>
          ) : (
            <div className="sources-empty">
              <div className="empty-file-icon">
                <FileText size={24} />
              </div>
              <strong>Пока нет источников</strong>
              <p>
                После ответа ассистента здесь появятся документы, пункты и
                цитаты, на которых основан вывод.
              </p>
            </div>
          )}
        </aside>
      )}

      {readerSource &&
        (readerSource.mimeType === "application/pdf" ||
         readerSource.title?.toLowerCase().endsWith(".pdf") ||
         readerSource.pdfUrl?.toLowerCase().endsWith(".pdf") ? (
          <PdfReader
            key={`pdf-${readerSource.id}`}
            source={readerSource}
            onClose={() => setReaderSource(null)}
          />
        ) : (
          <TextReader
            key={`text-${readerSource.id}`}
            source={readerSource}
            onClose={() => setReaderSource(null)}
          />
        ))}
    </main>
  )
}
