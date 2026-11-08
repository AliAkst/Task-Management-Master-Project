import { useEffect, type ReactNode } from 'react'

interface Props {
  title?: ReactNode
  onClose: () => void
  children: ReactNode
  wide?: boolean
  size?: 'md' | 'lg' | 'xl' // xl: kart detayi gibi iki sutunlu icerik (PC genisligi)
  label?: string // basliksiz pencereler icin erisilebilir ad
}

const WIDTH = { md: 'max-w-md', lg: 'max-w-3xl', xl: 'max-w-5xl' }

export default function Modal({ title, onClose, children, wide, size, label }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 sm:p-8"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : label}
        className={`w-full ${WIDTH[size ?? (wide ? 'lg' : 'md')]} rounded-xl bg-white p-6 shadow-[0_24px_64px_-16px_rgb(23_32_56/0.35)]`}
      >
        {title && <h2 className="mb-4 text-[22px]">{title}</h2>}
        {children}
      </div>
    </div>
  )
}
