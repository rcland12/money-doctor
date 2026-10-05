<script lang="ts">
	/** Leave balances (hours) on each pay statement, one line per kind, labelled at the end. */
	let { history, series }: { history: Record<string, any>[]; series: { key: string; label: string; color: string }[] } = $props();

	let width = $state(320);
	const W = $derived(Math.max(width, 280));
	const H = 190, L = 40, T = 12, B = 26;
	const R = $derived(W < 420 ? 12 : 140);
	const vals = $derived(history.flatMap((h) => series.map((s) => h[s.key]).filter((v) => typeof v === 'number')));
	const hi = $derived(Math.max(8, ...vals) * 1.1);
	const x = $derived((i: number) => L + (i / Math.max(history.length - 1, 1)) * (W - L - R));
	const y = $derived((v: number) => T + (1 - v / hi) * (H - T - B));
	const ticks = $derived.by(() => {
		const s = hi > 160 ? 80 : hi > 80 ? 40 : 20;
		const out = [];
		for (let v = 0; v <= hi; v += s) out.push(v);
		return out;
	});
	const path = (key: string) =>
		history
			.map((h, i) => (typeof h[key] === 'number' ? `${x(i).toFixed(1)},${y(h[key]).toFixed(1)}` : null))
			.filter(Boolean)
			.map((p, i) => (i ? 'L' : 'M') + p)
			.join('');
	const fmt = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
	const labels = $derived.by(() => {
		const out: number[] = [];
		history.forEach((_, i) => {
			if (!out.length || x(i) - x(out[out.length - 1]) > 64) out.push(i);
		});
		return out;
	});
	let hover: number | null = $state(null);
	function move(e: PointerEvent) {
		const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
		const i = Math.round(((((e.clientX - r.left) / r.width) * W - L) / (W - L - R)) * (history.length - 1));
		hover = Math.min(Math.max(i, 0), history.length - 1);
	}
	const last = $derived(history[history.length - 1] ?? {});
	// End labels, nudged apart so close balances don't overlap.
	const ends = $derived.by(() => {
		const out = series.filter((s) => typeof last[s.key] === 'number').map((s) => ({ ...s, v: last[s.key], ly: y(last[s.key]) + 4 }));
		out.sort((a, b) => a.ly - b.ly);
		for (let i = 1; i < out.length; i++) out[i].ly = Math.max(out[i].ly, out[i - 1].ly + 13);
		return out;
	});
</script>

<div class="relative w-full min-w-0 overflow-hidden" bind:clientWidth={width}>
	<svg width={W} height={H} class="block touch-none select-none" role="img" aria-label="Leave balances over time. Latest: {series.map((s) => `${s.label} ${history[history.length - 1]?.[s.key] ?? 'none'}h`).join(', ')}."
		onpointermove={move} onpointerleave={() => (hover = null)}>
		{#each ticks as t}
			<line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--line)" stroke-width="1" />
			<text x={L - 8} y={y(t) + 4} text-anchor="end" font-size="11" fill="var(--muted)">{t}h</text>
		{/each}
		{#each labels as i}
			<text x={x(i)} y={H - 7} text-anchor={i === 0 ? 'start' : 'middle'} font-size="11" fill="var(--muted)">{fmt(history[i].date)}</text>
		{/each}
		{#each series as s}
			<path d={path(s.key)} fill="none" stroke={s.color} stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
		{/each}
		{#if R > 40}
			{#each ends as e}
				<text x={x(history.length - 1) + 8} y={e.ly} font-size="11" fill="var(--ink-2)">{e.label} {e.v}h</text>
			{/each}
		{/if}
		{#if hover !== null}
			<line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="var(--ink-2)" stroke-width="1" />
			{#each series as s}
				{#if typeof history[hover][s.key] === 'number'}
					<circle cx={x(hover)} cy={y(history[hover][s.key])} r="4" fill={s.color} stroke="var(--surface)" stroke-width="2" />
				{/if}
			{/each}
		{/if}
	</svg>
	{#if hover !== null}
		<div aria-hidden="true" class="pointer-events-none absolute top-1 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs shadow-sm"
			style="left:{Math.min((x(hover) / W) * 100, 62)}%">
			<div class="text-muted">{new Date(history[hover].date + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</div>
			{#each series as s}
				{#if typeof history[hover][s.key] === 'number'}
					<div class="flex items-center justify-between gap-3">
						<span class="flex items-center gap-1.5"><span class="inline-block size-2 rounded-sm" style="background:{s.color}"></span>{s.label}</span>
						<span class="num font-semibold text-ink">{history[hover][s.key]}h</span>
					</div>
				{/if}
			{/each}
		</div>
	{/if}
	<div class="sr-only"><table>
		<caption>Leave balances, in hours, on each pay statement</caption>
		<thead><tr><th scope="col">Statement</th>{#each series as s}<th scope="col">{s.label}</th>{/each}</tr></thead>
		<tbody>
			{#each history as h}
				<tr><th scope="row">{h.date}</th>{#each series as s}<td>{typeof h[s.key] === 'number' ? `${h[s.key]}h` : 'none'}</td>{/each}</tr>
			{/each}
		</tbody>
	</table></div>
</div>
