import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import PaperTradingPage from './PaperTradingPage';
import * as paperTradingService from '../services/paperTrading';
import type { PaperAccountOut } from '../types/api';

vi.mock('../services/paperTrading');

const mockedGetAccount = vi.mocked(paperTradingService.getAccount);
const mockedListTransactions = vi.mocked(paperTradingService.listTransactions);
const mockedGetPerformance = vi.mocked(paperTradingService.getPerformance);
const mockedBuy = vi.mocked(paperTradingService.buy);

function neverResolves<T>() {
  return new Promise<T>(() => {});
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PaperTradingPage />
    </MemoryRouter>
  );
}

const emptyAccount: PaperAccountOut = {
  starting_cash: 1_000_000,
  cash_balance: 1_000_000,
  holdings_value: 0,
  total_value: 1_000_000,
  unrealized_pnl: 0,
  realized_pnl: 0,
  total_pnl: 0,
  total_return_pct: 0,
  holdings: [],
  data_source: 'DEV_SAMPLE',
  disclaimer: 'This is a hypothetical paper-trading account. No real money is involved.',
};

beforeEach(() => {
  vi.resetAllMocks();
  mockedListTransactions.mockResolvedValue([]);
  mockedGetPerformance.mockResolvedValue({
    points: [],
    benchmark_points: [],
    account_return_pct: 0,
    benchmark_return_pct: 0,
    data_source: 'DEV_SAMPLE',
    disclaimer: emptyAccount.disclaimer,
  });
});

describe('PaperTradingPage', () => {
  it('shows empty states when the account has no holdings or transactions', async () => {
    mockedGetAccount.mockResolvedValue(emptyAccount);
    renderPage();
    expect(await screen.findByText('No holdings yet')).toBeInTheDocument();
    expect(await screen.findByText('No transactions yet')).toBeInTheDocument();
    expect(screen.getByText(emptyAccount.disclaimer)).toBeInTheDocument();
  });

  it('shows a loading state while the account is fetched', () => {
    mockedGetAccount.mockReturnValue(neverResolves());
    const { container } = renderPage();
    expect(container.querySelector('.animate-spin')).not.toBeNull();
  });

  it('renders holdings and account totals', async () => {
    mockedGetAccount.mockResolvedValue({
      ...emptyAccount,
      cash_balance: 900_000,
      holdings_value: 105_000,
      total_value: 1_005_000,
      total_pnl: 5_000,
      total_return_pct: 0.5,
      holdings: [
        {
          symbol: 'TCS',
          name: 'Tata Consultancy Services',
          quantity: 10,
          avg_buy_price: 3500,
          current_price: 3550,
          invested_value: 35000,
          current_value: 35500,
          unrealized_pnl: 500,
          unrealized_pnl_pct: 1.43,
        },
      ],
    });
    renderPage();
    expect(await screen.findByText('TCS')).toBeInTheDocument();
    expect(screen.getByText('Tata Consultancy Services')).toBeInTheDocument();
  });

  it('submits a buy trade with the entered symbol and quantity', async () => {
    mockedGetAccount.mockResolvedValue(emptyAccount);
    mockedBuy.mockResolvedValue({
      id: 1,
      symbol: 'TCS',
      type: 'BUY',
      quantity: 10,
      price: 3550,
      fees: 12.5,
      realized_pnl: null,
      executed_at: '2026-11-11T10:00:00Z',
    });

    renderPage();
    await screen.findByText('No holdings yet');

    fireEvent.change(screen.getByPlaceholderText('e.g. TCS'), { target: { value: 'tcs' } });
    fireEvent.change(screen.getByPlaceholderText('e.g. 10'), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: 'Buy' }));

    await screen.findByRole('button', { name: /Buying|Buy/ });
    expect(mockedBuy).toHaveBeenCalledWith({ symbol: 'TCS', quantity: 10 });
  });
});
