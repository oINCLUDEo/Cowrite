import { useEffect, useRef, useState } from 'react'
import { api, apiResponse, type ExportAccepted, type ExportJob } from './api'

// PDF одной кнопкой: создать задание, опрашивать статус раз в 2 с и сразу скачать готовый файл.
// Состояние живёт в редакторе, а не в панели, поэтому задание не теряется, пока документ открыт.
export function usePdfExport(documentId: string, title: string) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  async function start() {
    setBusy(true)
    setError('')
    try {
      const { task_id: jobId } = await api<ExportAccepted>(`/documents/${documentId}/export`, { method: 'POST' })
      for (;;) {
        const job = await api<ExportJob>(`/exports/${jobId}`)
        if (!mounted.current) return
        if (job.status === 'succeeded') break
        if (job.status === 'failed') throw new Error('Не удалось создать PDF')
        await new Promise((resolve) => setTimeout(resolve, 2000))
      }
      const response = await apiResponse(`/exports/${jobId}/file`)
      const url = URL.createObjectURL(await response.blob())
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${title}.pdf`
      anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : 'Ошибка экспорта')
    } finally {
      if (mounted.current) setBusy(false)
    }
  }

  return { busy, error, start }
}
