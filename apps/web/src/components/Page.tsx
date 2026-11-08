import type { ReactNode } from 'react'

/**
 * Ajanda sayfasi iskeleti. Her sayfa ayni dili konusur:
 * buyuk baslik (sayfanin en buyuk ogesi) + tek satir aciklama + sagda islemler,
 * altinda ince bir cizgi. Bolumler kutu degil, cizgiyle ayrilir.
 */
export function PageHeader({
  title,
  subtitle,
  actions,
  before,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  before?: ReactNode // basligin ustunde (or. gun gezinme oklari)
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end gap-x-6 gap-y-3 border-b border-slate-200 pb-4">
      <div className="min-w-0">
        {before}
        <h1 className="text-[44px] leading-[1.05]">{title}</h1>
        {subtitle && <p className="mt-1.5 text-[15px] text-slate-600">{subtitle}</p>}
      </div>
      {actions && <div className="ml-auto flex flex-wrap items-center gap-3 pb-1">{actions}</div>}
    </header>
  )
}

export function Section({
  title,
  description,
  action,
  children,
  className = '',
}: {
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={className}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="text-[22px]">{title}</h2>
        {action}
      </div>
      {description && <p className="-mt-1.5 mb-4 max-w-prose text-[15px] text-slate-600">{description}</p>}
      {children}
    </section>
  )
}

/** Iki-uc secenekli anahtar (gorunum, aralik, mod). */
export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: { value: T; label: ReactNode; disabled?: boolean; title?: string }[]
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex rounded-lg bg-slate-200/70 p-0.5 text-sm">
      {options.map((o) => (
        <button
          key={String(o.value)}
          role="radio"
          aria-checked={value === o.value}
          disabled={o.disabled}
          title={o.title}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-3.5 py-1.5 disabled:opacity-40 ${
            value === o.value
              ? 'bg-white font-semibold text-slate-900 shadow-[0_0_0_1px_var(--color-slate-200)]'
              : 'text-slate-600 hover:text-slate-900'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
