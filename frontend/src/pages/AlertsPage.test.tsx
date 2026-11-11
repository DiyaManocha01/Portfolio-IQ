import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AlertsPage from './AlertsPage';
import * as alertService from '../services/alerts';

vi.mock('../services/alerts');

const mockedListRules = vi.mocked(alertService.listRules);
const mockedListEvents = vi.mocked(alertService.listEvents);
const mockedCreateRule = vi.mocked(alertService.createRule);

function neverResolves<T>() {
  return new Promise<T>(() => {});
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AlertsPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe('AlertsPage', () => {
  it('shows empty states when there are no rules or events', async () => {
    mockedListRules.mockResolvedValue([]);
    mockedListEvents.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText('No alert rules yet')).toBeInTheDocument();
    expect(await screen.findByText('No alerts yet')).toBeInTheDocument();
  });

  it('shows a loading state while rules are fetched', () => {
    mockedListRules.mockReturnValue(neverResolves());
    mockedListEvents.mockResolvedValue([]);
    const { container } = renderPage();
    expect(container.querySelector('.animate-spin')).not.toBeNull();
  });

  it('renders existing rules with their status', async () => {
    mockedListRules.mockResolvedValue([
      {
        id: 1,
        rule_type: 'PRICE_THRESHOLD',
        symbol: 'TCS',
        direction: 'ABOVE',
        threshold: 3500,
        enabled: true,
        last_value: 3490,
        last_evaluated_at: '2026-11-11T10:00:00Z',
        last_fired_at: null,
        created_at: '2026-11-11T09:00:00Z',
      },
    ]);
    mockedListEvents.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText('Price Threshold — TCS')).toBeInTheDocument();
    expect(screen.getByText('Enabled')).toBeInTheDocument();
  });

  it('renders triggered events with their explanation message', async () => {
    mockedListRules.mockResolvedValue([]);
    mockedListEvents.mockResolvedValue([
      {
        id: 1,
        rule_id: 1,
        rule_type: 'PRICE_THRESHOLD',
        symbol: 'TCS',
        triggered_at: '2026-11-11T10:00:00Z',
        value: 3510,
        message: 'TCS crossed above ₹3500.00 (now ₹3510.00)',
        is_read: false,
      },
    ]);
    renderPage();
    expect(await screen.findByText('TCS crossed above ₹3500.00 (now ₹3510.00)')).toBeInTheDocument();
    expect(screen.getByText('Mark read')).toBeInTheDocument();
  });

  it('submits a new rule with the entered fields', async () => {
    mockedListRules.mockResolvedValue([]);
    mockedListEvents.mockResolvedValue([]);
    mockedCreateRule.mockResolvedValue({
      id: 2,
      rule_type: 'PRICE_THRESHOLD',
      symbol: 'INFY',
      direction: 'ABOVE',
      threshold: 1800,
      enabled: true,
      last_value: null,
      last_evaluated_at: null,
      last_fired_at: null,
      created_at: '2026-11-11T09:00:00Z',
    });

    renderPage();
    await screen.findByText('No alert rules yet');

    fireEvent.change(screen.getByLabelText('Symbol'), { target: { value: 'infy' } });
    fireEvent.change(screen.getByLabelText('Price (₹)'), { target: { value: '1800' } });
    fireEvent.click(screen.getByText('Create Rule'));

    await screen.findByText(/Creating|Create Rule/);
    expect(mockedCreateRule).toHaveBeenCalledWith(
      expect.objectContaining({ rule_type: 'PRICE_THRESHOLD', symbol: 'INFY', direction: 'ABOVE', threshold: 1800 })
    );
  });
});
