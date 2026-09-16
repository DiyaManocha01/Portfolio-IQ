import type { NewsItem } from '../types/api';
import { SentimentBadge } from './Badge';
import { timeAgo } from '../utils/format';

export function NewsRow({ item, showSymbol = true }: { item: NewsItem; showSymbol?: boolean }) {
  const content = (
    <div className="flex items-start justify-between gap-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-100 leading-snug">{item.headline}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          {showSymbol && item.symbol && (
            <span className="rounded bg-base-surface2 px-1.5 py-0.5 font-semibold text-slate-300">{item.symbol}</span>
          )}
          <span>{item.source}</span>
          <span>&middot;</span>
          <span>{timeAgo(item.published_at)}</span>
        </div>
      </div>
      <SentimentBadge label={item.sentiment_label} />
    </div>
  );

  if (item.url) {
    return (
      <a href={item.url} target="_blank" rel="noreferrer" className="block border-b border-base-border last:border-0 hover:bg-base-surface2/50 -mx-2 px-2 rounded-md transition">
        {content}
      </a>
    );
  }
  return <div className="border-b border-base-border last:border-0">{content}</div>;
}
