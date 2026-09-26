export type AppRoute = 'home' | 'regflow' | 'runs' | 'regpacks' | 'organisation' | 'help'

export const routePaths: Record<AppRoute, string> = {
  home: '/',
  regflow: '/regflow',
  runs: '/runs',
  regpacks: '/regpacks',
  organisation: '/organisation',
  help: '/help',
}

export function routeFromPath(pathname: string): AppRoute {
  const normalised = `/${pathname.split('?')[0].split('#')[0].split('/').filter(Boolean).join('/')}`
  if (normalised === '/regflow') return 'regflow'
  if (normalised === '/runs') return 'runs'
  if (normalised === '/regpacks') return 'regpacks'
  if (normalised === '/organisation') return 'organisation'
  if (normalised === '/help') return 'help'
  return 'home'
}
