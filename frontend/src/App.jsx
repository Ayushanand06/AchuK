import { useState } from 'react'
import { setTheme, initialTheme } from './theme.js'
import AnalyticsPage from './pages/AnalyticsPage.jsx'
import MapPage from './pages/MapPage.jsx'
import OperationsDashboardPage from './pages/OperationsDashboardPage.jsx'
import ReviewConsolePage from './pages/ReviewConsolePage.jsx'
import PatrolPage from './pages/PatrolPage.jsx'
import LiveWallPage from './pages/LiveWallPage.jsx'

const PAGES = {
  dashboard: OperationsDashboardPage,
  live: LiveWallPage,
  review: ReviewConsolePage,
  patrol: PatrolPage,
  map: MapPage,
  analytics: AnalyticsPage,
}

export default function App() {
  const [page, setPage] = useState('dashboard')
  const [theme, setThemeState] = useState(initialTheme())

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    setThemeState(next)
  }

  const Page = PAGES[page] || OperationsDashboardPage
  return (
    <Page page={page} onNavigate={setPage} theme={theme} onToggleTheme={toggleTheme} />
  )
}
