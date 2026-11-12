import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import PortfolioPage from './PortfolioPage';
import * as portfolioService from '../services/portfolio';
import * as stockService from '../services/stocks';

vi.mock('../services/portfolio');
vi.mock('../services/stocks');

const mockedGetHoldings = vi.mocked(portfolioService.getHoldings);
const mockedGetStocks = vi.mocked(stockService.getStocks);
const mockedListTransactions = vi.mocked(portfolioService.listTransactions);
const mockedSellHolding = vi.mocked(portfolioService.sellHolding);

function neverResolves<T>() {
  return new Promise<T>(() => {});
}

const sampleHolding = {
  id: 1,
  symbol: 'TCS',
  name: 'Tata Consultancy Services',
  sector: 'Information Technology',
  quantity: 10,
  avg_buy_price: 3500,
  current_price: 3600,
  invested_value: 35000,
  current_value: 36000,
  pnl: 1000,
  return_pct: 2.86,
};

beforeEach(() => {
  vi.resetAllMocks();
  mockedGetStocks.mockResolvedValue([
    { id: 1, symbol: 'TCS', name: 'Tata Consultancy Services', sector: 'IT', industry: 'IT Services', exchange: 'NSE' },
  ]);
});

describe('PortfolioPage', () => {
  it('shows empty states for holdings and transactions', async () => {
    mockedGetHoldings.mockResolvedValue([]);
    mockedListTransactions.mockResolvedValue([]);
    render(<PortfolioPage />);
    expect(await screen.findByText('No holdings yet')).toBeInTheDocument();
    expect(await screen.findByText('No transactions yet')).toBeInTheDocument();
  });

  it('shows a loading state while holdings are fetched', () => {
    mockedGetHoldings.mockReturnValue(neverResolves());
    mockedListTransactions.mockResolvedValue([]);
    const { container } = render(<PortfolioPage />);
    expect(container.querySelector('.animate-pulse, .animate-spin')).not.toBeNull();
  });

  it('renders existing transactions with realized P&L', async () => {
    mockedGetHoldings.mockResolvedValue([sampleHolding]);
    mockedListTransactions.mockResolvedValue([
      { id: 2, symbol: 'TCS', type: 'SELL', quantity: 4, price: 3600, realized_pnl: 400, transaction_date: '2026-11-12' },
      { id: 1, symbol: 'TCS', type: 'BUY', quantity: 10, price: 3500, realized_pnl: null, transaction_date: '2026-11-10' },
    ]);
    render(<PortfolioPage />);
    expect(await screen.findByText('SELL')).toBeInTheDocument();
    expect(screen.getByText('BUY')).toBeInTheDocument();
  });

  it('submits a sell with the chosen holding, price, and quantity', async () => {
    mockedGetHoldings.mockResolvedValue([sampleHolding]);
    mockedListTransactions.mockResolvedValue([]);
    mockedSellHolding.mockResolvedValue({
      id: 2,
      symbol: 'TCS',
      type: 'SELL',
      quantity: 4,
      price: 3600,
      realized_pnl: 400,
      transaction_date: '2026-11-12',
    });

    render(<PortfolioPage />);
    await screen.findByText('No transactions yet');

    fireEvent.change(screen.getByText('Select a holding…').closest('select')!, { target: { value: '1' } });
    fireEvent.change(screen.getByPlaceholderText('e.g. 3600'), { target: { value: '3600' } });
    fireEvent.change(screen.getByPlaceholderText('Leave blank to sell the entire position'), { target: { value: '4' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sell' }));

    await screen.findByText(/Sold 4 shares of TCS/);
    expect(mockedSellHolding).toHaveBeenCalledWith(1, { price: 3600, quantity: 4 });
  });
});
