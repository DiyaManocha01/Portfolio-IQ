import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './hooks/useAuth';
import { ProtectedRoute } from './layouts/ProtectedRoute';
import { AppLayout } from './layouts/AppLayout';

import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import DashboardPage from './pages/DashboardPage';
import PortfolioPage from './pages/PortfolioPage';
import StocksPage from './pages/StocksPage';
import StockDetailPage from './pages/StockDetailPage';
import DiscoverPage from './pages/DiscoverPage';
import PortfolioFitPage from './pages/PortfolioFitPage';
import IntelligencePage from './pages/IntelligencePage';

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/portfolio" element={<PortfolioPage />} />
            <Route path="/stocks" element={<StocksPage />} />
            <Route path="/stocks/:symbol" element={<StockDetailPage />} />
            <Route path="/discover" element={<DiscoverPage />} />
            <Route path="/discover/:symbol" element={<PortfolioFitPage />} />
            <Route path="/intelligence" element={<IntelligencePage />} />
          </Route>

          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
