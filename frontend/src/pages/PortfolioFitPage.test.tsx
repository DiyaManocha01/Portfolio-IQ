import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import PortfolioFitPage from './PortfolioFitPage';
import * as discoverService from '../services/discover';
import * as stockService from '../services/stocks';

vi.mock('../services/discover');
vi.mock('../services/stocks');

const mockedGetPortfolioFit = vi.mocked(discoverService.getPortfolioFit);
const mockedCompareFit = vi.mocked(discoverService.compareFit);
const mockedGetFitCounterfactual = vi.mocked(discoverService.getFitCounterfactual);
const mockedGetStocks = vi.mocked(stockService.getStocks);

function renderFitPage() {
  return render(
    <MemoryRouter initialEntries={['/discover/TCS']}>
      <Routes>
        <Route path="/discover/:symbol" element={<PortfolioFitPage />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mockedGetPortfolioFit.mockResolvedValue({
    symbol: 'TCS',
    name: 'Tata Consultancy Services',
    fit_score: 80,
    factors: [{ name: 'ML Outlook', contribution: 0.2, explanation: 'Model outlook is positive.' }],
    strengths: ['Diversifies away from current holdings.'],
    concerns: [],
    weights_used: { outlook: 0.25 },
  });
  mockedGetStocks.mockResolvedValue([
    { id: 1, symbol: 'TCS', name: 'Tata Consultancy Services', sector: 'IT', industry: 'IT Services', exchange: 'NSE' },
    { id: 2, symbol: 'INFY', name: 'Infosys', sector: 'IT', industry: 'IT Services', exchange: 'NSE' },
  ]);
});

describe('PortfolioFitPage - Compare to Another Stock', () => {
  it('renders the compare and counterfactual section headings once fit data loads', async () => {
    renderFitPage();
    expect(await screen.findByText('Compare to Another Stock')).toBeInTheDocument();
    expect(screen.getByText('What Would Improve This Fit?')).toBeInTheDocument();
  });

  it('disables Compare until a stock is selected, then renders the comparison', async () => {
    mockedCompareFit.mockResolvedValue({
      symbol_a: 'TCS',
      symbol_b: 'INFY',
      fit_score_a: 80,
      fit_score_b: 60,
      logit_gap: 0.5,
      term_deltas: [{ term: 'ml_outlook', name: 'ML Outlook', contribution_a: 0.2, contribution_b: 0.1, delta: 0.1 }],
      preset: 'balanced',
      note: 'term_deltas sum exactly to logit_gap.',
    });

    const user = userEvent.setup();
    renderFitPage();
    await screen.findByText('Compare to Another Stock');

    const compareButton = screen.getByRole('button', { name: 'Compare' });
    expect(compareButton).toBeDisabled();

    const [compareSelect] = await screen.findAllByRole('combobox');
    await user.selectOptions(compareSelect, 'INFY');
    expect(compareButton).toBeEnabled();

    await user.click(compareButton);

    expect(mockedCompareFit).toHaveBeenCalledWith('TCS', 'INFY');
    expect(await screen.findByText('term_deltas sum exactly to logit_gap.')).toBeInTheDocument();
  });
});

describe('PortfolioFitPage - What Would Improve This Fit?', () => {
  it('runs a target-score scenario and renders the term scenarios', async () => {
    mockedGetFitCounterfactual.mockResolvedValue({
      symbol: 'TCS',
      fit_score: 80,
      target: 'score 90',
      already_meets_target: false,
      term_scenarios: [
        { term: 'ml_outlook', name: 'ML Outlook', current_raw_value: 0.5, required_z_delta: 0.3, required_raw_delta: 0.1, target_raw_value: 0.6 },
      ],
      note: 'Each scenario is CETERIS PARIBUS.',
    });

    const user = userEvent.setup();
    renderFitPage();
    await screen.findByText('What Would Improve This Fit?');

    await user.click(screen.getByRole('button', { name: 'Reach a target score' }));
    const scoreInput = screen.getByPlaceholderText('e.g. 75');
    await user.type(scoreInput, '90');
    await user.click(screen.getByRole('button', { name: 'Run' }));

    expect(mockedGetFitCounterfactual).toHaveBeenCalledWith('TCS', { targetScore: 90 });
    expect(await screen.findByText('Each scenario is CETERIS PARIBUS.')).toBeInTheDocument();
  });
});
