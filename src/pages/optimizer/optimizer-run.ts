import type { OptimizerConfig } from '@/lib/types'

/**
 * The config as it is sent to the optimizer. Weights that are all zero mean "no weights", so they become null.
 * @param config The config shown in the panel.
 * @returns The config to run.
 */
export function runnableConfig(config: OptimizerConfig): OptimizerConfig {
  const sw = config.stat_weights
  const hasWeights = sw != null && Object.values(sw).some((v) => v !== 0)
  return { ...config, stat_weights: hasWeights ? sw : null }
}
