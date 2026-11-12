import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MarketPage from './MarketPage';
import * as marketService from '../services/market';
import { useMarketFeed } from '../hooks/useMarketFeed';

vi.mock('../services/market');
vi.mock('../hooks/useMarketFeed');

const mockedGetMarketStatus = vi.mocked(marketService.getMarketStatus);
const mockedGetRegime = vi.mocked(marketService.getRegime);
const mockedUseMarketFeed = vi.mocked(useMarketFeed);

function neverResolves<T>() {
  return new Promise<T>(() => {});
}

function renderPage() {
  return render(
    <MemoryRouter>
      <MarketPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mockedUseMarketFeed.mockReturnValue({ connection: 'connecting', data: null });
  mockedGetRegime.mockResolvedValue({
    symbol: 'NIFTY50',
    regime: 'SIDEWAYS',
    display_name: 'Sideways',
    confidence: 0.3,
    factors: [],
    as_of: '2026-11-11',
    note: null,
    data_source: 'DEV_SAMPLE',
  });
});

describe('MarketPage', () => {
  it('shows a loading state before the initial status arrives', () => {
    mockedGetMarketStatus.mockReturnValue(neverResolves());
    renderPage();
    expect(screen.getByText('Loading market status…')).toBeInTheDocument();
  });

  it('shows an empty state when the status loads with no ticks yet', async () => {
    mockedGetMarketStatus.mockResolvedValue({
      market_status: 'CLOSED',
      feed_status: 'DISABLED',
      server_time: '2026-11-11T10:00:00Z',
      ticks: [],
    });
    renderPage();
    expect(await screen.findByText('No prices yet')).toBeInTheDocument();
  });

  it('renders watchlist cards, gainers and losers once ticks arrive', async () => {
    mockedGetMarketStatus.mockResolvedValue({
      market_status: 'OPEN',
      feed_status: 'CONNECTED',
      server_time: '2026-11-11T10:00:00Z',
      ticks: [
        {
          symbol: 'RELIANCE',
          exchange: 'NSE',
          price: 2960.5,
          previous_close: 2950,
          change: 10.5,
          change_percent: 0.36,
          open: 2951,
          high: 2965,
          low: 2948,
          close: 2950,
          volume: 1200000,
          last_traded_time: '2026-11-11T10:00:00Z',
          status: 'LIVE',
          source: 'ANGELONE',
        },
        {
          symbol: 'TCS',
          exchange: 'NSE',
          price: 3400,
          previous_close: 3450,
          change: -50,
          change_percent: -1.45,
          open: 3440,
          high: 3445,
          low: 3395,
          close: 3450,
          volume: 800000,
          last_traded_time: '2026-11-11T10:00:00Z',
          status: 'FIXTURE',
          source: 'FIXTURE',
        },
      ],
    });

    renderPage();

    expect(await screen.findAllByText('RELIANCE')).not.toHaveLength(0);
    expect(screen.getAllByText('TCS').length).toBeGreaterThan(0);
  });

  it('renders the NIFTY 50 market regime card once it loads', async () => {
    mockedGetMarketStatus.mockResolvedValue({
      market_status: 'CLOSED',
      feed_status: 'DISABLED',
      server_time: '2026-11-11T10:00:00Z',
      ticks: [],
    });
    mockedGetRegime.mockResolvedValue({
      symbol: 'NIFTY50',
      regime: 'TRENDING_UP',
      display_name: 'Trending Upward',
      confidence: 0.72,
      factors: [{ name: 'Trend', raw_value: 0.08, z_score: 1.5, explanation: 'Markets are trending upward.' }],
      as_of: '2026-11-11',
      note: null,
      data_source: 'DEV_SAMPLE',
    });
    renderPage();
    expect(await screen.findByText('Trending Upward')).toBeInTheDocument();
    expect(screen.getByText(/Markets are trending upward\./)).toBeInTheDocument();
  });

  it('prefers live WebSocket data over the initial REST snapshot once it arrives', async () => {
    mockedGetMarketStatus.mockResolvedValue({
      market_status: 'CLOSED',
      feed_status: 'DISABLED',
      server_time: '2026-11-11T10:00:00Z',
      ticks: [],
    });
    mockedUseMarketFeed.mockReturnValue({
      connection: 'open',
      data: {
        market_status: 'OPEN',
        feed_status: 'CONNECTED',
        server_time: '2026-11-11T10:00:01Z',
        ticks: [
          {
            symbol: 'WIPRO',
            exchange: 'NSE',
            price: 550,
            previous_close: 545,
            change: 5,
            change_percent: 0.92,
            open: 546,
            high: 552,
            low: 544,
            close: 545,
            volume: 500000,
            last_traded_time: '2026-11-11T10:00:01Z',
            status: 'LIVE',
            source: 'ANGELONE',
          },
        ],
      },
    });

    renderPage();
    expect((await screen.findAllByText('WIPRO')).length).toBeGreaterThan(0);
  });
});
