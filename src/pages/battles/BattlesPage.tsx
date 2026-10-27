import { useState } from 'react'
import { NavLink, Outlet, useMatch } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { enemyDecrease, enemyLabel, loadEnemy, saveEnemy, type BattlesContext, type SimEnemy } from './battles-enemy'

const TABS = [
  { to: 'simulate', key: 'battles.tabs.simulate' },
  { to: 'overview', key: 'battles.tabs.overview' },
  { to: 'analytics', key: 'battles.tabs.analytics' },
  { to: 'history', key: 'battles.tabs.history' },
] as const

/**
 * The strip under the tabs naming the enemy the Simulator will use.
 * @param enemy The current Simulator enemy.
 * @returns The enemy bar.
 */
function EnemyBar({ enemy }: { enemy: SimEnemy }) {
  const { t } = useTranslation()
  const decrease = enemyDecrease(enemy)
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-[#282828] bg-[#161616] px-4 py-1.5 text-[11px]">
      <span className="text-[11px] uppercase tracking-wide text-[#8a8a8a]">{t('battles.enemy.title')}</span>
      <span className="text-[#e5e7eb]">{enemyLabel(enemy)}</span>
      <span className="font-mono text-[#b3b3b3]">DEF {enemy.def}</span>
      <span className="font-mono text-[#b3b3b3]">{t('battles.enemy.decrease', { pct: (decrease * 100).toFixed(1) })}</span>
      <span className="text-[#8a8a8a]">{enemy.dmgDecrease > 0 ? t('battles.enemy.gameData') : t('battles.enemy.estimated')}</span>
      <span className="ml-auto font-mono text-[#fb923c]">{((1 - decrease) * 100).toFixed(1)}% {t('simulator.dmgPasses')}</span>
    </div>
  )
}

/**
 * The Battles page: the Simulator and the captured battle history under one tab bar, sharing the Simulator enemy.
 * @returns The page shell with the current tab in its outlet.
 */
export function BattlesPage() {
  const { t } = useTranslation()
  const [enemy, setEnemyState] = useState(loadEnemy)
  const onSimulate = useMatch('/battles/simulate') != null

  const context: BattlesContext = {
    enemy,
    setEnemy: (next) => { setEnemyState(next); saveEnemy(next) },
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex shrink-0 items-center gap-1 border-b border-[#282828] bg-[#121212] px-3">
        <h2 className="mr-3 text-sm font-bold text-[#ffffff]">{t('nav.battles')}</h2>
        {TABS.map(tab => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              cn(
                '-mb-px border-b-2 px-3 py-2.5 text-xs font-bold uppercase tracking-wide transition-colors',
                isActive
                  ? 'border-[#c084fc] text-[#ffffff]'
                  : 'border-transparent text-[#888] hover:text-[#e5e7eb]',
              )
            }
          >
            {t(tab.key)}
          </NavLink>
        ))}
      </div>
      {onSimulate && <EnemyBar enemy={enemy} />}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <Outlet context={context} />
      </div>
    </div>
  )
}
