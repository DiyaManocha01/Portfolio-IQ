import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import IntelligencePage from './IntelligencePage';
import * as portfolioService from '../services/portfolio';

vi.mock('../services/portfolio');

const mockedGetRisk = vi.mocked(portfolioService.getRisk);
const mockedGetRiskAttribution = vi.mocked(portfolioService.getRiskAttribution);
const mockedGetAdvancedPerformance = vi.mocked(portfolioService.getAdvancedPerformance);
const mockedGetHealth = vi.mocked(portfolioService.getHealth);
const mockedGetWeaknesses = vi.mocked(portfolioService.getWeaknesses);

function neverResolves<T>() {
  return new Promise<T>(() => {});
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe('IntelligencePage - Risk Attribution section', () => {
  it('shows a loading state before data arrives', () => {
    mockedGetRisk.mockReturnValue(neverResolves());
    mockedGetRiskAttribution.mockReturnValue(neverResolves());
    mockedGetAdvancedPerformance.mockReturnValue(neverResolves());
    mockedGetHealth.mockReturnValue(neverResolves());
    mockedGetWeaknesses.mockReturnValue(neverResolves());

    render(<IntelligencePage />);
    expect(screen.getByText('Risk Attribution')).toBeInTheDocument();
  });

  it('renders attribution rows once data loads', async () => {
    mockedGetRisk.mockReturnValue(neverResolves());
    mockedGetAdvancedPerformance.mockReturnValue(neverResolves());
    mockedGetHealth.mockReturnValue(neverResolves());
    mockedGetWeaknesses.mockReturnValue(neverResolves());
    mockedGetRiskAttribution.mockResolvedValue({
      portfolio_annualized_volatility: 0.2,
      data_source: 'DEV_SAMPLE',
      attributions: [
        {
          symbol: 'TCS',
          name: 'Tata Consultancy Services',
          sector: 'Information Technology',
          weight_pct: 25,
          risk_contribution_pct: 30,
          marginal_contribution_to_vol: 0.05,
          risk_concentration_ratio: 1.2,
        },
      ],
    });

    render(<IntelligencePage />);

    expect(await screen.findByText('TCS')).toBeInTheDocument();
    expect(screen.getByText('25.00%')).toBeInTheDocument();
    expect(screen.getByText('30.00%')).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.textContent === '1.2x')).toBeInTheDocument();
  });

  it('renders an error state with a retry affordance', async () => {
    mockedGetRisk.mockReturnValue(neverResolves());
    mockedGetAdvancedPerformance.mockReturnValue(neverResolves());
    mockedGetHealth.mockReturnValue(neverResolves());
    mockedGetWeaknesses.mockReturnValue(neverResolves());
    mockedGetRiskAttribution.mockRejectedValue(new Error('Network error'));

    render(<IntelligencePage />);

    expect(await screen.findByText('Network error')).toBeInTheDocument();
  });
});

describe('IntelligencePage - Advanced Performance section', () => {
  it('renders realized/unrealized/total P&L once data loads', async () => {
    mockedGetRisk.mockReturnValue(neverResolves());
    mockedGetRiskAttribution.mockReturnValue(neverResolves());
    mockedGetHealth.mockReturnValue(neverResolves());
    mockedGetWeaknesses.mockReturnValue(neverResolves());
    mockedGetAdvancedPerformance.mockResolvedValue({
      points: [{ date: '2026-11-01', value: 100000, invested: 95000 }],
      daily_returns: [{ date: '2026-11-01', return_pct: 0.5 }],
      cumulative_returns: [{ date: '2026-11-01', cumulative_return_pct: 5.3 }],
      drawdown: [{ date: '2026-11-01', drawdown_pct: -2.1 }],
      benchmark: [{ date: '2026-11-01', value: 99000 }],
      holding_contributions: [{ symbol: 'TCS', name: 'Tata Consultancy Services', pnl: 5000, contribution_pct: 100 }],
      sector_contributions: [{ sector: 'Information Technology', pnl: 5000, contribution_pct: 100 }],
      unrealized_pnl: 5000,
      realized_pnl: 0,
      total_pnl: 5000,
      annualized_volatility_realized: 0.18,
      data_source: 'DEV_SAMPLE',
    });

    render(<IntelligencePage />);

    expect(await screen.findByText('Advanced Performance')).toBeInTheDocument();
    expect(screen.getByText('Portfolio vs. NIFTY 50')).toBeInTheDocument();
  });
});
