import type { CorrelationEntry } from '../types/api';

function correlationColor(v: number): string {
  // -1 -> red, 0 -> neutral slate, 1 -> green
  if (v >= 0) {
    const alpha = Math.min(1, v) * 0.75 + 0.08;
    return `rgba(34,197,94,${alpha.toFixed(2)})`;
  }
  const alpha = Math.min(1, -v) * 0.75 + 0.08;
  return `rgba(248,113,113,${alpha.toFixed(2)})`;
}

export function CorrelationHeatmap({ matrix }: { matrix: CorrelationEntry[] }) {
  const symbols = Array.from(new Set(matrix.flatMap((m) => [m.symbol_a, m.symbol_b]))).sort();
  const lookup = new Map<string, number>();
  matrix.forEach((m) => {
    lookup.set(`${m.symbol_a}|${m.symbol_b}`, m.correlation);
    lookup.set(`${m.symbol_b}|${m.symbol_a}`, m.correlation);
  });

  function valueFor(a: string, b: string): number {
    if (a === b) return 1;
    return lookup.get(`${a}|${b}`) ?? 0;
  }

  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-1 text-[11px]">
        <thead>
          <tr>
            <th className="w-16" />
            {symbols.map((s) => (
              <th key={s} className="px-1 py-1 text-center font-medium text-slate-400">
                {s}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {symbols.map((rowSym) => (
            <tr key={rowSym}>
              <th className="pr-2 text-right font-medium text-slate-400 whitespace-nowrap">{rowSym}</th>
              {symbols.map((colSym) => {
                const v = valueFor(rowSym, colSym);
                return (
                  <td key={colSym} className="p-0">
                    <div
                      title={`${rowSym} vs ${colSym}: ${v.toFixed(2)}`}
                      className="flex h-9 w-12 items-center justify-center rounded-md text-[11px] font-medium text-slate-100"
                      style={{ backgroundColor: correlationColor(v) }}
                    >
                      {v.toFixed(2)}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
