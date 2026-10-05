export function money(x: number | null | undefined, cents = true): string {
	if (x === null || x === undefined || Number.isNaN(x)) return '—';
	const s = Math.abs(x).toLocaleString('en-US', { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 });
	return `${x < 0 ? '−' : ''}$${s}`;
}

export function day(iso: string, today?: string): string {
	const d = new Date(iso + 'T12:00:00');
	if (today) {
		const diff = Math.round((d.getTime() - new Date(today + 'T12:00:00').getTime()) / 86400000);
		if (diff === 0) return 'Today';
		if (diff === 1) return 'Tomorrow';
		if (diff > 1 && diff < 7) return d.toLocaleDateString('en-US', { weekday: 'short', month: 'numeric', day: 'numeric' });
	}
	return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function monthName(ym: string, long = true): string {
	const [y, m] = ym.split('-').map(Number);
	return new Date(y, m - 1, 15).toLocaleDateString('en-US', { month: long ? 'long' : 'short', year: 'numeric' });
}

export function shiftMonth(ym: string, n: number): string {
	const [y, m] = ym.split('-').map(Number);
	const d = new Date(y, m - 1 + n, 15);
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** Status for a budget line: text + colour role, never colour alone. */
export function paceOf(line: { kind: string; pace?: string; spent: number; target: number }) {
	if (line.kind !== 'variable') return null;
	if (line.pace === 'over') return { label: 'Over', role: 'bad' };
	if (line.pace === 'ahead') return { label: 'Ahead of pace', role: 'warn' };
	return { label: 'On pace', role: 'good' };
}
