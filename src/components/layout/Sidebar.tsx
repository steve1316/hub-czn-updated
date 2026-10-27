import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Home, Swords, Layers, Users, SquareStack,
  Radio, Wrench, History, Info, Crosshair, BookOpen, BookMarked, type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUpdateCheck } from '@/hooks/useUpdateCheck'


// Pages in the order a new player needs them. A group without a label sits on its own.
const NAV_GROUPS = [
  { label: null, items: [
    { to: '/',           key: 'nav.home',        icon: Home },
  ] },
  { label: 'nav.groups.start', items: [
    { to: '/setup',      key: 'nav.setup',       icon: Wrench },
    { to: '/capture',    key: 'nav.capture',     icon: Radio },
  ] },
  { label: 'nav.groups.account', items: [
    { to: '/fragments',  key: 'nav.fragments',   icon: Layers },
    { to: '/combatants', key: 'nav.combatants',  icon: Users },
    { to: '/rescue',     key: 'nav.rescue',      icon: History },
  ] },
  { label: 'nav.groups.tools', items: [
    { to: '/optimizer',  key: 'nav.optimizer',   icon: Swords },
    { to: '/deck-builder', key: 'nav.deckBuilder', icon: SquareStack, beta: true },
    { to: '/battles',    key: 'nav.battles',     icon: Crosshair, beta: true },
  ] },
  { label: 'nav.groups.reference', items: [
    { to: '/encyclopedia', key: 'nav.encyclopedia', icon: BookOpen },
    { to: '/guides',     key: 'nav.guides',      icon: BookMarked },
  ] },
] as const

const ABOUT = { to: '/about', key: 'nav.about', icon: Info }

export function Sidebar() {
  const { t } = useTranslation()
  const { hasUpdate } = useUpdateCheck()

  /**
   * One sidebar link.
   * @param item The page to link to, with an optional beta flag.
   * @returns The link element.
   */
  const renderItem = ({ to, key, icon: Icon, beta }: { to: string, key: string, icon: LucideIcon, beta?: boolean }) => (
    <NavLink
      key={to}
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-3 border-l-[3px] px-4 py-2 text-sm transition-colors rounded-none',
          isActive
            ? 'border-[#c084fc] text-[#ffffff] bg-[#282828] font-bold'
            : 'border-transparent text-[#b3b3b3] hover:text-[#ffffff] hover:bg-[#282828]',
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon size={16} className={isActive ? 'text-[#c084fc]' : undefined} />
          <span className="flex-1">{t(key)}</span>
          {beta && (
            <span className="text-[11px] font-semibold px-1.5 rounded-full bg-[#c084fc]/20 text-[#c084fc] shrink-0">
              {t('nav.beta')}
            </span>
          )}
          {key === 'nav.about' && hasUpdate && (
            <span className="w-2 h-2 rounded-full bg-[#c084fc] shrink-0" />
          )}
        </>
      )}
    </NavLink>
  )

  return (
    <nav className="w-52 shrink-0 h-full flex flex-col overflow-y-auto bg-[#181818] py-4">
      <div className="px-4 mb-4">
        <span className="text-[#ffffff] font-bold text-base tracking-wide">Hub CZN</span>
      </div>
      {NAV_GROUPS.map(({ label, items }) => (
        <div key={label ?? 'top'} className="flex flex-col">
          {label && <div className="px-4 pt-3 pb-1 text-xs font-semibold text-[#8a8a8a]">{t(label)}</div>}
          {items.map(renderItem)}
        </div>
      ))}
      <div className="mt-auto pt-3">{renderItem(ABOUT)}</div>
    </nav>
  )
}
