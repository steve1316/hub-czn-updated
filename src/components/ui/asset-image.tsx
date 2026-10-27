import { useEffect, useRef, useState } from "react"
import type { ImgHTMLAttributes, ReactNode } from "react"
import { ImageOff } from "lucide-react"
import { MAX_IMAGE_RETRIES, imageRetryDelay, imageRetryUrl } from "@/lib/imageRetry"

/** Props for `AssetImage`. Takes the normal `<img>` props plus an optional fallback. */
interface AssetImageProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, "src"> {
  /** Full image url, usually from `assetUrl()`. */
  src: string
  /** Shown once all retries have failed. Defaults to a dark neutral placeholder sized by `className`. Pass `null` to render nothing. */
  fallback?: ReactNode
  /** How many times to retry a failed load before giving up. Defaults to `MAX_IMAGE_RETRIES`. */
  maxRetries?: number
  /** Called once, after the last retry has failed (not on each retry). */
  onError?: ImgHTMLAttributes<HTMLImageElement>["onError"]
}

/**
 * An `<img>` that loads lazily and retries failed loads with backoff before showing a placeholder.
 * @param props The `<img>` props, plus `fallback` for a custom failure view.
 * @returns The image, or the fallback after the last retry fails.
 */
export function AssetImage({ src, fallback, maxRetries = MAX_IMAGE_RETRIES, className, onError, alt = "", ...rest }: AssetImageProps) {
  const [state, setState] = useState({ src, attempt: 0, failed: false })
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // A new src starts over. Derived during render so no effect has to set state.
  if (state.src !== src) setState({ src, attempt: 0, failed: false })
  const { attempt, failed } = state.src === src ? state : { attempt: 0, failed: false }

  // Cancel a pending retry on unmount or when src changes.
  useEffect(() => () => clearTimeout(timer.current), [src])

  if (failed) {
    if (fallback !== undefined) return <>{fallback}</>
    return (
      <div className={`${className ?? ""} flex items-center justify-center bg-[#282828] text-[#8a8a8a]`} role="img" aria-label={alt}>
        <ImageOff className="h-1/2 w-1/2 max-h-4 max-w-4" />
      </div>
    )
  }

  return (
    <img
      {...rest}
      src={imageRetryUrl(src, attempt)}
      alt={alt}
      className={className}
      loading="lazy"
      decoding="async"
      onError={(e) => {
        if (attempt >= maxRetries) {
          onError?.(e)
          setState({ src, attempt, failed: true })
          return
        }
        clearTimeout(timer.current)
        timer.current = setTimeout(() => setState({ src, attempt: attempt + 1, failed: false }), imageRetryDelay(attempt + 1))
      }}
    />
  )
}
