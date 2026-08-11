import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import ExtractionReview from './pages/ExtractionReview'
import ScenarioConfig from './pages/ScenarioConfig'
import ResultScreen from './pages/ResultScreen'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/documents/:documentId/review" element={<ExtractionReview />} />
        <Route path="/documents/:documentId/scenarios" element={<ScenarioConfig />} />
        <Route path="/documents/:documentId/results" element={<ResultScreen />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
