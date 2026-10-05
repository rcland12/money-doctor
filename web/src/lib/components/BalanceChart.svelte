<script lang="ts">
	import { money } from '$lib/format';

	/** Projected checking balance by day. One series, a dashed cushion line, the
	    lowest point marked; crosshair + tooltip on hover. */
	let { days, cushion, lowest }: { days: { date: string; end: number }[]; cushion: number; lowest: { date: string; balance: number } | null } = $props();

	let width = $state(320); // replaced by the container's real width on mount
	const W = $derived(Math.max(width, 280));
	const H = 200, L = 52, R = 12, T = 14, B = 26;
	const vals = $derived(days.map((d) => d.end));
	const lo = $derived(Math.min(0, cushion, ...vals));
	const hi = $derived(Math.max(cushion, ...vals) * 1.08);
	const x = $derived((i: number) => L + (i / Math.max(days.length - 1, 1)) * (W - L - R));
	const y = $derived((v: number) => T + (1 - (v - lo) / Math.max(hi - lo, 1)) * (H - T - B));
	const path = $derived(days.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d.end).toFixed(1)}`).join(''));
	const ticks = $derived.by(() => {
		const step = hi - lo > 4000 ? 2000 : 1000;
		const out = [];
		for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
		return out;
	});
	const fmt = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	const labels = $derived.by(() => {
		const out: number[] = [];
		days.forEach((_, i) => {
			if (i % 7 === 0 && (!out.length || x(i) - x(out[out.length - 1]) > 56)) out.push(i);
		});
		return out;
	});
	const summary = $derived(
		days.length
			? `Projected checking balance by day, ${fmt(days[0].date)} to ${fmt(days[days.length - 1].date)}: starts at ${money(days[0].end, false)}` +
					(lowest ? `, lowest ${money(lowest.balance, false)} on ${fmt(lowest.date)}` : '') +
					`, ends at ${money(days[days.length - 1].end, false)}. Cushion ${money(cushion, false)}.`
			: 'No forecast yet.'
	);
	const lowIdx = $derived(lowest ? days.findIndex((d) => d.date === lowest.date) : -1);

	let hover: number | null = $state(null);
	function move(e: PointerEvent) {
		const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
		const i = Math.round((((e.clientX - r.left) / r.width) * W - L) / (W - L - R) * (days.length - 1));
		hover = Math.min(Math.max(i, 0), days.length - 1);
	}
</script>

<div class="relative w-full min-w-0 overflow-hidden" bind:clientWidth={width}>
	<svg width={W} height={H} class="block touch-none select-none" role="img" aria-label={summary}
		onpointermove={move} onpointerleave={() => (hover = null)}>
		{#each ticks as t}
			<line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--line)" stroke-width="1" />
			<text x={L - 8} y={y(t) + 4} text-anchor="end" font-size="11" fill="var(--muted)">{t === 0 ? '$0' : `$${(t / 1000).toFixed(t % 1000 ? 1 : 0)}k`}</text>
		{/each}
		{#each labels as i}
			<text x={x(i)} y={H - 7} text-anchor={i === 0 ? 'start' : 'middle'} font-size="11" fill="var(--muted)">{fmt(days[i].date)}</text>
		{/each}
		<line x1={L} x2={W - R} y1={y(cushion)} y2={y(cushion)} stroke="var(--warn)" stroke-width="1.5" stroke-dasharray="4 4" />
		<text x={L + 4} y={y(cushion) - 5} text-anchor="start" font-size="11" fill="var(--ink-2)">cushion {money(cushion, false)}</text>
		<path d={path} fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
		{#if lowIdx >= 0 && hover === null}
			<circle cx={x(lowIdx)} cy={y(days[lowIdx].end)} r="4.5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2" />
			<text x={Math.min(x(lowIdx), W - R - 70)} y={y(days[lowIdx].end) + 18} font-size="11" fill="var(--ink-2)">lowest {money(days[lowIdx].end, false)}</text>
		{/if}
		{#if hover !== null}
			<line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="var(--ink-2)" stroke-width="1" />
			<circle cx={x(hover)} cy={y(days[hover].end)} r="4.5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2" />
		{/if}
	</svg>
	{#if hover !== null}
		<div aria-hidden="true" class="pointer-events-none absolute top-1 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-sm"
			style="left:{Math.min((x(hover) / W) * 100, 68)}%">
			<div class="text-muted">{fmt(days[hover].date)}</div>
			<div class="num font-semibold text-ink">{money(days[hover].end)}</div>
		</div>
	{/if}
</div>
