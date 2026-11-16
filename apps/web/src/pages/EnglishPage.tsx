import { useState } from 'react'
import { useEnglishProfile } from '../api/english'
import { PageHeader } from '../components/Page'
import EnglishSettings from '../components/english/EnglishSettings'
import MistakesTab from '../components/english/MistakesTab'
import PracticeTab from '../components/english/PracticeTab'
import ProgressTab from '../components/english/ProgressTab'
import SetupForm from '../components/english/SetupForm'
import TodayTab from '../components/english/TodayTab'

const TABS = [
  { id: 'today', label: 'Bugün' },
  { id: 'practice', label: 'Pratik' },
  { id: 'mistakes', label: 'Hata günlüğü' },
  { id: 'progress', label: 'İlerleme' },
  { id: 'settings', label: 'Ayarlar' },
] as const
type TabId = (typeof TABS)[number]['id']

export default function EnglishPage() {
  const profile = useEnglishProfile()
  const [tab, setTab] = useState<TabId>('today')

  if (profile.isPending) {
    return <div className="mx-auto w-full max-w-3xl p-4 sm:p-6 text-slate-600">Yükleniyor…</div>
  }
  if (profile.isError) {
    return (
      <div className="mx-auto w-full max-w-3xl p-4 sm:p-6">
        <p role="alert" className="text-red-700">İngilizce verisi yüklenemedi.</p>
      </div>
    )
  }

  // Profil yok (404) -> ilk kurulum
  if (!profile.data) {
    return (
      <div className="mx-auto w-full max-w-3xl p-4 sm:p-6">
        <PageHeader title="İngilizce" subtitle="Başlamadan önce üç şey soralım." />
        <SetupForm />
      </div>
    )
  }

  const p = profile.data
  return (
    <div className="mx-auto w-full max-w-3xl p-4 sm:p-6">
      <PageHeader
        title="İngilizce"
        actions={
          <span className="rounded-full border border-slate-300 bg-surface px-3 py-1 text-sm font-semibold">
            {p.current_level ?? '?'} → {p.target_level}
          </span>
        }
      />
      <div role="tablist" aria-label="İngilizce bölümleri" className="-mx-4 mb-6 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`shrink-0 rounded-lg px-3.5 py-1.5 text-[15px] ${
              tab === t.id
                ? 'bg-surface font-semibold text-slate-900 shadow-[0_0_0_1px_var(--color-slate-200)]'
                : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === 'today' && <TodayTab onPractice={() => setTab('practice')} />}
        {tab === 'practice' && <PracticeTab />}
        {tab === 'mistakes' && <MistakesTab />}
        {tab === 'progress' && <ProgressTab />}
        {tab === 'settings' && <EnglishSettings profile={p} />}
      </div>
    </div>
  )
}
