import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PortfolioLabPage from './PortfolioLabPage';
import * as portfolioService from '../services/portfolio';
import * as stockService from '../services/stocks';

vi.mock('../services/portfolio');
vi.mock('../services/stocks');

const mockedGetHoldings = vi.mocked(portfolioService.getHoldings);
const mockedGetStocks = vi.mocked(stockService.getStocks);
const mockedPostWhatIf = vi.mocked(portfolioService.postWhatIf);
const mockedGetOptimization = vi.mocked(portfolioService.getOptimization);

const holding = {
  id: 1,
  symbol: 'TCS',
  name: 'Tata Consultancy Services',
  sector: 'Information Technology',
  quantity: 10,
  avg_buy_price: 3000,
  current_price: 3500,
  invested_value: 30000,
  current_value: 35000,
  pnl: 5000,
  return_pct: 16.67,
};

beforeEach(() => {
  vi.resetAllMocks();
  mockedGetHoldings.mockResolvedValue([holding]);
  mockedGetStocks.mockResolvedValue([]);
});

describe('PortfolioLabPage - What-If Simulator tab', () => {
  it('renders the held symbol with its current quantity', async () => {
    render(<PortfolioLabPage />);
    expect(await screen.findByText('TCS')).toBeInTheDocument();
    expect(screen.getByText('currently 10')).toBeInTheDocument();
  });

  it('shows a validation error when nothing has changed', async () => {
    const user = userEvent.setup();
    render(<PortfolioLabPage />);
    await screen.findByText('TCS');

    await user.click(screen.getByRole('button', { name: 'Simulate' }));

    expect(await screen.findByText(/change at least one quantity/i)).toBeInTheDocument();
    expect(mockedPostWhatIf).not.toHaveBeenCalled();
  });

  it('submits a changed quantity and renders the before/after result', async () => {
    mockedPostWhatIf.mockResolvedValue({
      before: {
        annualized_volatility: 0.2,
        sharpe_ratio: 0.5,
        var_95: -0.03,
        cvar_95: -0.05,
        var_99: -0.07,
        cvar_99: -0.09,
        diversification_ratio: 1.1,
        hhi_holdings: 0.3,
      },
      after: {
        annualized_volatility: 0.22,
        sharpe_ratio: 0.4,
        var_95: -0.04,
        cvar_95: -0.06,
        var_99: -0.08,
        cvar_99: -0.1,
        diversification_ratio: 1.0,
        hhi_holdings: 0.35,
      },
      deltas: {},
      trades: [
        {
          symbol: 'TCS',
          quantity_delta: 5,
          trade_value: 17500,
          action: 'buy',
          estimated_cost: {
            brokerage: 10,
            stt: 5,
            stamp_duty: 1,
            exchange_charges: 1,
            sebi_fee: 1,
            gst: 2,
            total: 20,
          },
        },
      ],
      total_estimated_cost: 20,
      risk_free_rate_assumed: 0.06,
      lookback_days: 252,
      data_source: 'DEV_SAMPLE',
      disclaimer: 'This is a hypothetical simulation.',
    });

    const user = userEvent.setup();
    render(<PortfolioLabPage />);
    await screen.findByText('TCS');

    const qtyInput = screen.getByPlaceholderText('10');
    await user.clear(qtyInput);
    await user.type(qtyInput, '15');
    await user.click(screen.getByRole('button', { name: 'Simulate' }));

    expect(mockedPostWhatIf).toHaveBeenCalledWith([{ symbol: 'TCS', new_quantity: 15 }], true);
    expect(await screen.findByText('This is a hypothetical simulation.')).toBeInTheDocument();
    expect(screen.getByText('BUY')).toBeInTheDocument();
  });
});

describe('PortfolioLabPage - Optimization tab', () => {
  it('runs the optimizer and renders the suggested allocation', async () => {
    mockedGetOptimization.mockResolvedValue({
      method: 'min_variance',
      feasible: true,
      note: null,
      allocations: [{ symbol: 'TCS', current_weight_pct: 100, suggested_weight_pct: 80, delta_pct: -20 }],
      expected_annual_return: 0.1,
      expected_annual_volatility: 0.15,
      expected_sharpe_ratio: 0.5,
      risk_free_rate_assumed: 0.06,
      lookback_days: 252,
      data_source: 'DEV_SAMPLE',
      disclaimer: 'This is a hypothetical target allocation.',
    });

    const user = userEvent.setup();
    render(<PortfolioLabPage />);
    await user.click(screen.getByRole('button', { name: 'Optimization' }));
    await user.click(screen.getByRole('button', { name: 'Suggest Allocation' }));

    expect(mockedGetOptimization).toHaveBeenCalledWith('min_variance');
    expect(await screen.findByText('This is a hypothetical target allocation.')).toBeInTheDocument();
    expect(screen.getByText('Expected Sharpe')).toBeInTheDocument();
  });

  it('renders an infeasibility note instead of results', async () => {
    mockedGetOptimization.mockResolvedValue({
      method: 'max_sharpe',
      feasible: false,
      note: 'Not enough holdings to optimize.',
      allocations: [],
      expected_annual_return: 0,
      expected_annual_volatility: 0,
      expected_sharpe_ratio: 0,
      risk_free_rate_assumed: 0.06,
      lookback_days: 252,
      data_source: 'DEV_SAMPLE',
      disclaimer: '',
    });

    const user = userEvent.setup();
    render(<PortfolioLabPage />);
    await user.click(screen.getByRole('button', { name: 'Optimization' }));
    await user.click(screen.getByRole('button', { name: 'Suggest Allocation' }));

    expect(await screen.findByText(/Not enough holdings to optimize/i)).toBeInTheDocument();
  });
});
