type PlatformStatusProps = {
  connected: boolean | null
}

export function PlatformStatus({ connected }: PlatformStatusProps) {
  const label = connected === false ? 'API unavailable' : 'API connected'
  const state = connected === null ? 'checking' : connected ? 'connected' : 'unavailable'

  return (
    <section className="platform-status" aria-live="polite">
      <span className={`status-dot status-dot--${state}`} aria-hidden="true" />
      <div>
        <span className="status-label">System status</span>
        <strong>{connected === null ? 'Checking API…' : label}</strong>
      </div>
    </section>
  )
}
