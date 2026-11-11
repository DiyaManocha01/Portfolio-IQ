import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ScreenerPage from './ScreenerPage';
import * as stockService from '../services/stocks';
import * as screenerService from '../services/screener';

vi.mock('../services/stocks');
vi.mock('../services/screener');

const mockedGetStocks = vi.mocked(stockService.getStocks);
const mockedRunScreener = vi.mocked(screenerService.runScreener);

function neverResolves<T>() {
  return new Promise<T>(() => {});
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ScreenerPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mockedGetStocks.mockResolvedValue([
    { id: 1, symbol: 'TCS', name: 'Tata Consultancy Services', sector: 'Information Technology', industry: 'IT Services', exchange: 'NSE' },
    { id: 2, symbol: 'RELIANCE', name: 'Reliance Industries', sector: 'Energy', industry: 'Oil & Gas', exchange: 'NSE' },
  ]);
});

describe('ScreenerPage', () => {
  it('shows a loading state while the screener runs', () => {
    mockedRunScreener.mockReturnValue(neverResolves());
    renderPage();
    expect(screen.getByText('Running screener…')).toBeInTheDocument();
  });

  it('shows an empty state when nothing matches', async () => {
    mockedRunScreener.mockResolvedValue({ count: 0, results: [], disclaimer: 'x' });
    renderPage();
    expect(await screen.findByText('No matches')).toBeInTheDocument();
  });

  it('renders a results table when matches are returned', async () => {
    mockedRunScreener.mockResolvedValue({
      count: 1,
      results: [
        {
          symbol: 'TCS',
          name: 'Tata Consultancy Services',
          sector: 'Information Technology',
          industry: 'IT Services',
          data_source: 'DEV_SAMPLE',
          current_price: 3450,
          market_cap: 8.1e12,
          pe_ratio: 25.8,
          eps: 133.6,
          dividend_yield: 2.47,
          roe: 0.1535,
          roce: 0.2194,
          debt_to_equity: 46.24,
          revenue_growth_yoy: 0.2076,
          profit_growth_yoy: 0.2744,
          rsi_14: 55.2,
          momentum_10d: 0.03,
        },
      ],
      disclaimer: 'x',
    });

    renderPage();
    expect(await screen.findByText('TCS')).toBeInTheDocument();
    expect(screen.getByText('1 match')).toBeInTheDocument();
  });

  it('re-runs the screener with the entered filters on submit', async () => {
    mockedRunScreener.mockResolvedValue({ count: 0, results: [], disclaimer: 'x' });
    renderPage();
    await screen.findByText('No matches');

    const peMinInput = screen.getByLabelText('P/E Min');
    fireEvent.change(peMinInput, { target: { value: '10' } });
    fireEvent.click(screen.getByText('Apply Filters'));

    expect(mockedRunScreener).toHaveBeenLastCalledWith(expect.objectContaining({ pe_min: 10 }));
  });
});
