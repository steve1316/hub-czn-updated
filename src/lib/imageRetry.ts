/** How many times a failed image load is retried before the placeholder is shown. */
export const MAX_IMAGE_RETRIES = 3

/** Delay before the first retry in milliseconds, doubled on each later retry. */
const BASE_RETRY_DELAY_MS = 500

/**
 * Build the url for a given load attempt. Retries get a changing query param so the browser does not reuse a cached failure.
 * @param src The original image url.
 * @param attempt Zero for the first load, then 1..`MAX_IMAGE_RETRIES` for retries.
 * @returns The url to load.
 */
export function imageRetryUrl(src: string, attempt: number): string {
  if (attempt <= 0) return src
  return `${src}${src.includes("?") ? "&" : "?"}_retry=${attempt}`
}

/**
 * Wait time before a retry.
 * @param attempt The retry number, starting at 1.
 * @returns Milliseconds to wait (500, 1000, 2000).
 */
export function imageRetryDelay(attempt: number): number {
  return BASE_RETRY_DELAY_MS * 2 ** (attempt - 1)
}
