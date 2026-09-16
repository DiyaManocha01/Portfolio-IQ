import clsx from 'clsx';
import type { Holding } from '../types/api';
import { formatCurrency, formatNumber, formatSignedPct } from '../utils/format';

export function HoldingsTable({
  holdings,
  onRemove,
  removing,
}: {
  holdings: Holding[];
  onRemove?: (holding: Holding) => void;
  removing?: number | null;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-b border-base-border text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="py-2 pr-4 font-medium">Stock</th>
            <th className="py-2 pr-4 font-medium text-right">Quantity</th>
            <th className="py-2 pr-4 font-medium text-right">Price</th>
            <th className="py-2 pr-4 font-medium text-right">Value</th>
            <th className="py-2 pr-4 font-medium text-right">P&amp;L</th>
            <th className="py-2 pr-4 font-medium text-right">Return</th>
            {onRemove && <th className="py-2 pl-2 font-medium text-right">Action</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-base-border">
          {holdings.map((h) => {
            const positive = h.pnl >= 0;
            return (
              <tr key={h.id} className="hover:bg-base-surface2/60 transition">
                <td className="py-3 pr-4">
                  <div className="font-semibold text-slate-100">{h.symbol}</div>
                  <div className="text-xs text-slate-500">{h.name}</div>
                </td>
                <td className="py-3 pr-4 text-right text-slate-300">{formatNumber(h.quantity)}</td>
                <td className="py-3 pr-4 text-right text-slate-300">{formatCurrency(h.current_price)}</td>
                <td className="py-3 pr-4 text-right font-medium text-slate-100">{formatCurrency(h.current_value)}</td>
                <td className={clsx('py-3 pr-4 text-right font-medium', positive ? 'text-positive' : 'text-negative')}>
                  {positive ? '+' : ''}
                  {formatCurrency(h.pnl)}
                </td>
                <td className={clsx('py-3 pr-4 text-right font-medium', positive ? 'text-positive' : 'text-negative')}>
                  {formatSignedPct(h.return_pct)}
                </td>
                {onRemove && (
                  <td className="py-3 pl-2 text-right">
                    <button
                      onClick={() => onRemove(h)}
                      disabled={removing === h.id}
                      className="rounded-md border border-base-border px-2.5 py-1 text-xs font-medium text-slate-400 hover:border-negative/40 hover:text-negative transition disabled:opacity-50"
                    >
                      {removing === h.id ? 'Removing…' : 'Remove'}
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
