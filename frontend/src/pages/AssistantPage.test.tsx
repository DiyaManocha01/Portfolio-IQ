import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AssistantPage from './AssistantPage';
import * as assistantService from '../services/assistant';

vi.mock('../services/assistant');

const mockedAsk = vi.mocked(assistantService.askAssistant);

function neverResolves<T>() {
  return new Promise<T>(() => {});
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe('AssistantPage', () => {
  it('shows an empty state before any question is asked', () => {
    render(<AssistantPage />);
    expect(screen.getByText(/No messages yet/)).toBeInTheDocument();
  });

  it('submits a question and renders the answer with sources and disclaimer', async () => {
    mockedAsk.mockResolvedValue({
      answer: 'Your portfolio is up 2.3% today.',
      sources_used: ['portfolio_summary'],
      guardrail_tripped: false,
      guardrail_matched_phrase: null,
      model: 'claude-sonnet-5',
      disclaimer: 'This is not financial advice.',
    });

    render(<AssistantPage />);
    fireEvent.change(screen.getByLabelText('Ask the assistant a question'), {
      target: { value: 'How is my portfolio doing today?' },
    });
    fireEvent.click(screen.getByText('Ask'));

    expect(await screen.findByText('Your portfolio is up 2.3% today.')).toBeInTheDocument();
    expect(screen.getByText('How is my portfolio doing today?')).toBeInTheDocument();
    expect(screen.getByText('portfolio_summary')).toBeInTheDocument();
    expect(screen.getByText('This is not financial advice.')).toBeInTheDocument();
    expect(mockedAsk).toHaveBeenCalledWith('How is my portfolio doing today?');
  });

  it('shows a guardrail badge when the response was adjusted', async () => {
    mockedAsk.mockResolvedValue({
      answer: 'I can share analysis, but not buy/sell advice.',
      sources_used: [],
      guardrail_tripped: true,
      guardrail_matched_phrase: 'you should buy',
      model: 'claude-sonnet-5',
      disclaimer: 'This is not financial advice.',
    });

    render(<AssistantPage />);
    fireEvent.change(screen.getByLabelText('Ask the assistant a question'), { target: { value: 'Should I buy TCS?' } });
    fireEvent.click(screen.getByText('Ask'));

    expect(await screen.findByText(/Guardrail: response adjusted/)).toBeInTheDocument();
  });

  it('shows a thinking indicator while waiting for a response', () => {
    mockedAsk.mockReturnValue(neverResolves());
    render(<AssistantPage />);
    fireEvent.change(screen.getByLabelText('Ask the assistant a question'), { target: { value: 'What is my risk level?' } });
    fireEvent.click(screen.getByText('Ask'));
    expect(screen.getByText('Thinking…')).toBeInTheDocument();
  });

  it('shows an error message when the request fails', async () => {
    mockedAsk.mockRejectedValue(new Error('Rate limit exceeded'));
    render(<AssistantPage />);
    fireEvent.change(screen.getByLabelText('Ask the assistant a question'), { target: { value: 'Hello' } });
    fireEvent.click(screen.getByText('Ask'));
    expect(await screen.findByText('Rate limit exceeded')).toBeInTheDocument();
  });

  it('does not submit an empty or whitespace-only question', () => {
    render(<AssistantPage />);
    const askButton = screen.getByText('Ask');
    expect(askButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Ask the assistant a question'), { target: { value: '   ' } });
    expect(askButton).toBeDisabled();
    expect(mockedAsk).not.toHaveBeenCalled();
  });
});
