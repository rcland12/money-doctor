<script lang="ts">
	import { money, monthName } from '$lib/format';

	/** Projected total card balance by month. One series, so the title names it
	    and there is no legend. A crosshair + tooltip follows the pointer. */
	let { series, target }: { series: { month: string; total: number }[]; target: string | null } = $props();

	// Drawn at the container's real width so text stays 11px on every screen.
	let width = $state(320); // replaced by the container's real width on mount
	const W = $derived(Math.max(width, 280));
	const H = 220, L = 52, R = 12, T = 12, B = 28;
	const max = $derived(Math.max(...series.map((p) => p.total), 1));
	const niceMax = $derived(Math.ceil(max / 5000) * 5000);
	const x = $derived((i: number) => L + (i / Math.max(series.length - 1, 1)) * (W - L - R));
	const y = (v: number) => T + (1 - v / niceMax) * (H - T - B);
	const path = $derived(series.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.total).toFixed(1)}`).join(''));
	const ticks = $derived([0, 0.25, 0.5, 0.75, 1].map((f) => f * niceMax));
	const summary = $derived(
		series.length
			? `Projected credit card balance by month: ${money(series[0].total, false)} in ${monthName(series[0].month)}, ` +
					`${money(series[series.length - 1].total, false)} by ${monthName(series[series.length - 1].month)}` +
					(target ? `. Target: ${monthName(target)}.` : '.')
			: 'No projection yet.'
	);
	const targetIdx = $derived(target ? series.findIndex((p) => p.month === target) : -1);
	// Start month + each January, dropping any label that would collide with the one before it.
	const years = $derived.by(() => {
		const out: { i: number; p: { month: string; total: number } }[] = [];
		series.forEach((p, i) => {
			if ((i === 0 || p.month.endsWith('-01')) && (!out.length || x(i) - x(out[out.length - 1].i) > 70)) out.push({ i, p });
		});
		return out;
	});

	let hover: number | null = $state(null);
	function move(e: PointerEvent) {
		const svg = e.currentTarget as SVGSVGElement;
		const r = svg.getBoundingClientRect();
		const px = ((e.clientX - r.left) / r.width) * W;
		const i = Math.round(((px - L) / (W - L - R)) * (series.length - 1));
		hover = Math.min(Math.max(i, 0), series.length - 1);
	}
</script>

<div class="relative w-full min-w-0 overflow-hidden" bind:clientWidth={width}>
	<svg
		viewBox="0 0 {W} {H}"
		width={W}
		height={H}
		class="block touch-none select-none"
		role="img"
		aria-label={summary}
		onpointermove={move}
		onpointerleave={() => (hover = null)}
	>
		{#each ticks as t}
			<line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--line)" stroke-width="1" />
			<text x={L - 8} y={y(t) + 4} text-anchor="end" font-size="11" fill="var(--muted)" class="num">
				{t >= 1000 ? `$${t / 1000}k` : '$0'}
			</text>
		{/each}
		{#each years as { i, p }}
			<text x={x(i)} y={H - 8} text-anchor={i === 0 ? 'start' : 'middle'} font-size="11" fill="var(--muted)">
				{i === 0 ? monthName(p.month, false) : p.month.slice(0, 4)}
			</text>
		{/each}
		{#if targetIdx >= 0}
			<line x1={x(targetIdx)} x2={x(targetIdx)} y1={T} y2={H - B} stroke="var(--ink-2)" stroke-width="1" stroke-dasharray="3 3" />
			<text x={x(targetIdx) - 4} y={T + 10} text-anchor="end" font-size="11" fill="var(--ink-2)">target</text>
		{/if}
		<path d={path} fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
		{#if hover !== null}
			<line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="var(--ink-2)" stroke-width="1" />
			<circle cx={x(hover)} cy={y(series[hover].total)} r="4.5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2" />
		{/if}
	</svg>
	{#if hover !== null}
		<div
			aria-hidden="true"
			class="pointer-events-none absolute top-1 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-sm"
			style="left:{Math.min((x(hover) / W) * 100, 70)}%"
		>
			<div class="text-muted">{monthName(series[hover].month)}</div>
			<div class="num font-semibold text-ink">{money(series[hover].total, false)}</div>
		</div>
	{/if}
	<div class="sr-only"><table>
		<caption>Projected credit card balance by month</caption>
		<thead><tr><th scope="col">Month</th><th scope="col">Balance</th></tr></thead>
		<tbody>
			{#each series as p}<tr><th scope="row">{monthName(p.month)}</th><td>{money(p.total, false)}</td></tr>{/each}
		</tbody>
	</table></div>
</div>
