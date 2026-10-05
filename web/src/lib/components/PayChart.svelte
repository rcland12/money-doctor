<script lang="ts">
	import { money } from '$lib/format';

	/** One stacked bar per paycheck: take-home at the bottom, then what came out
	    of gross. Bar height = gross. Hover for the split. */
	type Check = { date: string; gross: number; net: number; taxes: number; retirement: number; insurance: number; other: number };
	let { checks, series }: { checks: Check[]; series: { key: keyof Check; label: string; color: string }[] } = $props();

	let width = $state(320);
	const W = $derived(Math.max(width, 280));
	const H = 220, L = 46, R = 8, T = 12, B = 26;
	const hi = $derived(Math.max(...checks.map((c) => c.gross), 1) * 1.08);
	const step = $derived((W - L - R) / Math.max(checks.length, 1));
	const bw = $derived(Math.max(3, Math.min(28, step * 0.7)));
	const y = $derived((v: number) => T + (1 - v / hi) * (H - T - B));
	const ticks = $derived.by(() => {
		const s = hi > 8000 ? 2000 : 1000;
		const out = [];
		for (let v = 0; v <= hi; v += s) out.push(v);
		return out;
	});
	const fmt = (iso: string, o: Intl.DateTimeFormatOptions = { month: 'short' }) => new Date(iso + 'T12:00:00').toLocaleDateString('en-US', o);
	// Month labels: the first check of each month, when there's room.
	const labels = $derived.by(() => {
		const out: number[] = [];
		checks.forEach((c, i) => {
			if ((i === 0 || c.date.slice(0, 7) !== checks[i - 1].date.slice(0, 7)) && (!out.length || (i - out[out.length - 1]) * step > 34)) out.push(i);
		});
		return out;
	});

	let hover: number | null = $state(null);
	function move(e: PointerEvent) {
		const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
		const i = Math.floor((((e.clientX - r.left) / r.width) * W - L) / step);
		hover = i >= 0 && i < checks.length ? i : null;
	}
</script>

<div class="relative w-full min-w-0 overflow-hidden" bind:clientWidth={width}>
	<svg width={W} height={H} class="block touch-none select-none" role="img" aria-label="Gross pay per paycheck, split into take-home and deductions. {checks.length} paychecks; the same numbers are in the table that follows."
		onpointermove={move} onpointerleave={() => (hover = null)}>
		{#each ticks as t}
			<line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--line)" stroke-width="1" />
			<text x={L - 8} y={y(t) + 4} text-anchor="end" font-size="11" fill="var(--muted)">{t === 0 ? '$0' : `$${(t / 1000).toFixed(0)}k`}</text>
		{/each}
		{#each checks as c, i}
			{@const cx = L + step * i + step / 2}
			{#each series as s, k}
				{@const below = series.slice(0, k).reduce((a, x) => a + (c[x.key] as number), 0)}
				{@const v = c[s.key] as number}
				{#if v > 0}
					<rect x={cx - bw / 2} y={y(below + v)} width={bw} height={Math.max(0, y(below) - y(below + v) - (k ? 1 : 0))}
						fill={s.color} opacity={hover === null || hover === i ? 1 : 0.45} rx={k === series.length - 1 ? 2 : 0} />
				{/if}
			{/each}
		{/each}
		{#each labels as i}
			<text x={L + step * i + step / 2} y={H - 7} text-anchor="middle" font-size="11" fill="var(--muted)">{fmt(checks[i].date)}</text>
		{/each}
	</svg>
	{#if hover !== null}
		{@const c = checks[hover]}
		<div aria-hidden="true" class="pointer-events-none absolute top-1 min-w-40 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-sm"
			style="left:{Math.min(((L + step * hover) / W) * 100, 58)}%">
			<div class="text-muted">Paid {fmt(c.date, { month: 'short', day: 'numeric', year: 'numeric' })}</div>
			<div class="flex justify-between gap-3 font-semibold text-ink"><span>Gross</span><span class="num">{money(c.gross)}</span></div>
			{#each [...series].reverse() as s}
				{#if (c[s.key] as number) > 0}
					<div class="flex items-center justify-between gap-3">
						<span class="flex items-center gap-1.5"><span class="inline-block size-2 rounded-sm" style="background:{s.color}"></span>{s.label}</span>
						<span class="num">{money(c[s.key] as number)}</span>
					</div>
				{/if}
			{/each}
		</div>
	{/if}
	<div class="sr-only"><table>
		<caption>Each paycheck</caption>
		<thead><tr><th scope="col">Paid</th><th scope="col">Gross</th>{#each series as s}<th scope="col">{s.label}</th>{/each}</tr></thead>
		<tbody>
			{#each checks as c}
				<tr>
					<th scope="row">{fmt(c.date, { month: 'short', day: 'numeric', year: 'numeric' })}</th>
					<td>{money(c.gross)}</td>
					{#each series as s}<td>{money(c[s.key] as number)}</td>{/each}
				</tr>
			{/each}
		</tbody>
	</table></div>
</div>
