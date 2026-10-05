<script lang="ts">
	import { api } from '$lib/api.svelte';
	import { money, monthName } from '$lib/format';
	import PayChart from '$lib/components/PayChart.svelte';
	import LeaveChart from '$lib/components/LeaveChart.svelte';

	let year = $state<number | null>(null);
	let d: any = $state(null);
	let err = $state('');
	$effect(() => {
		api(`/v1/income${year ? `?year=${year}` : ''}`)
			.then((r) => {
				d = r;
				year ??= r.year;
			})
			.catch((e) => (err = e.message));
	});

	const SERIES = [
		{ key: 'net', label: 'Take-home', color: 'var(--accent)' },
		{ key: 'taxes', label: 'Taxes', color: 'var(--s-tax)' },
		{ key: 'retirement', label: 'Retirement', color: 'var(--s-retire)' },
		{ key: 'insurance', label: 'Insurance', color: 'var(--s-insure)' },
		{ key: 'other', label: 'Other deductions', color: 'var(--s-other)' }
	] as const;
	const color = (key: string) => SERIES.find((s) => s.key === key)?.color ?? 'var(--s-other)';
	const LEAVE_COLORS = ['var(--accent)', 'var(--s-insure)', 'var(--s-tax)', 'var(--s-retire)'];

	const split = $derived(d ? [{ key: 'net', name: 'Take-home', amount: d.net, items: [] }, ...d.deductions] : []);
	const extra = $derived(d ? d.earnings.filter((e: any) => e.kind !== 'regular').reduce((s: number, e: any) => s + e.amount, 0) : 0);
	const leaveSeries = $derived(
		d?.leave
			? d.leave.kinds
					.filter((k: any) => k.balance !== null && d.leave.history.some((h: any) => typeof h[k.kind] === 'number'))
					.map((k: any, i: number) => ({ key: k.kind, label: k.name.replace(/ \(.*\)/, ''), color: LEAVE_COLORS[i % 4] }))
			: []
	);
	const otherGroups = $derived(
		d ? ['Other income', 'Paid back'].map((k) => ({ k, rows: d.other.filter((o: any) => o.kind === k) })).filter((g) => g.rows.length) : []
	);
	const pct = (x: number) => (d.gross ? `${((x / d.gross) * 100).toFixed(1)}%` : '');
	const hours = (h: number | null) => (h === null || h === undefined ? '—' : `${h % 1 ? h.toFixed(1) : h}h`);
	const days = (h: number) => `${(h / 8).toFixed(h % 8 ? 1 : 0)} days`;
	const dateLong = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
</script>

<div class="flex flex-wrap items-center justify-between gap-3">
	<h1 class="text-xl font-semibold">Income</h1>
	{#if d}
		<select bind:value={year} aria-label="Year">
			{#each d.years as y}<option value={y}>{y}</option>{/each}
		</select>
	{/if}
</div>
{#if err}<p class="mt-3 text-bad-ink" role="alert">{err}</p>{/if}

{#if d}
	{#if d.count === 0}
		<p class="card mt-3 p-4 text-sm text-muted">No pay statements for {d.year} yet. Upload them on the Upload page and they'll show up here.</p>
	{:else}
		<p class="mt-1 text-sm text-muted">
			From {d.count} pay statement{d.count === 1 ? '' : 's'}, {dateLong(d.checks[0].date)} to {dateLong(d.checks[d.checks.length - 1].date)}{d.first_statement > `${d.year}-01-14` ? ` (the earliest one on file)` : ''}.
		</p>

		<!-- Totals -->
		<div class="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
			<div class="card p-4">
				<div class="label">Gross pay</div>
				<div class="num mt-1 text-2xl font-semibold">{money(d.gross, false)}</div>
				<div class="text-xs text-muted">Before taxes and deductions</div>
			</div>
			<div class="card p-4">
				<div class="label">Take-home</div>
				<div class="num mt-1 text-2xl font-semibold">{money(d.net, false)}</div>
				<div class="text-xs text-muted">You kept {(d.kept * 100).toFixed(1)}% of gross</div>
			</div>
			<div class="card p-4">
				<div class="label">Overtime and bonuses</div>
				<div class="num mt-1 text-2xl font-semibold">{money(extra, false)}</div>
				<div class="text-xs text-muted">Gross, on top of regular pay</div>
			</div>
			{#if d.projection}
				<div class="card p-4">
					<div class="label">{d.year} on pace for</div>
					<div class="num mt-1 text-2xl font-semibold">{money(d.projection.gross, false)}</div>
					<div class="text-xs text-muted"><span class="num">{money(d.projection.net, false)}</span> take-home, with {d.projection.checks_left} regular paychecks left</div>
				</div>
			{:else}
				<div class="card p-4">
					<div class="label">Average paycheck</div>
					<div class="num mt-1 text-2xl font-semibold">{money(d.net / d.count, false)}</div>
					<div class="text-xs text-muted">Take-home, <span class="num">{money(d.gross / d.count, false)}</span> gross</div>
				</div>
			{/if}
		</div>

		<!-- Over time -->
		<section class="card mt-4 p-5">
			<div class="flex flex-wrap items-baseline justify-between gap-2">
				<h2 class="label">Each paycheck</h2>
				<div class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-2">
					{#each SERIES.filter((s) => s.key === 'net' || d.deductions.some((g: any) => g.key === s.key)) as s}
						<span class="flex items-center gap-1.5"><span class="inline-block size-2.5 rounded-sm" aria-hidden="true" style="background:{s.color}"></span>{s.label}</span>
					{/each}
				</div>
			</div>
			<div class="mt-3"><PayChart checks={d.checks} series={[...SERIES]} /></div>
			<p class="mt-2 text-xs text-muted">Each bar is one paycheck's gross pay. Taller bars are overtime, bonuses, or holiday pay.</p>
		</section>

		<div class="mt-4 grid gap-4 md:grid-cols-2">
			<!-- Where it goes -->
			<section class="card p-5">
				<h2 class="label">Where your gross pay goes</h2>
				<div class="mt-3 flex h-3 overflow-hidden rounded-full" role="img"
					aria-label="Gross pay split: {split.map((g) => `${g.name} ${pct(g.amount)}`).join(', ')}">
					{#each split as g}
						<div style="width:{(g.amount / d.gross) * 100}%;background:{color(g.key)}" class="border-r border-surface last:border-0"></div>
					{/each}
				</div>
				<ul class="mt-3 text-sm">
					{#each split as g}
						<li class="border-b border-line py-2 last:border-0">
							{#if g.items.length}
								<details class="group">
									<summary class="flex list-none items-center gap-2">
										<span class="inline-block size-2.5 rounded-sm" aria-hidden="true" style="background:{color(g.key)}"></span>
										<span class="flex-1">{g.name} <span class="text-xs text-muted">({g.items.length})</span></span>
										<span class="w-14 text-right text-xs text-muted">{pct(g.amount)}</span>
										<span class="num w-24 text-right font-semibold">{money(g.amount, false)}</span>
									</summary>
									<ul class="mt-1 ml-4.5 text-ink-2">
										{#each g.items as it}
											<li class="flex py-0.5"><span class="flex-1">{it.name}</span><span class="num w-24 text-right">{money(it.amount)}</span></li>
										{/each}
									</ul>
								</details>
							{:else}
								<div class="flex items-center gap-2">
									<span class="inline-block size-2.5 rounded-sm" aria-hidden="true" style="background:{color(g.key)}"></span>
									<span class="flex-1 font-semibold">{g.name}</span>
									<span class="w-14 text-right text-xs text-muted">{pct(g.amount)}</span>
									<span class="num w-24 text-right font-semibold">{money(g.amount, false)}</span>
								</div>
							{/if}
						</li>
					{/each}
				</ul>
				<p class="mt-2 text-xs text-muted">Select a group to see each deduction.</p>
			</section>

			<!-- What you earned -->
			<section class="card p-5">
				<h2 class="label">What you earned</h2>
				<ul class="mt-3 text-sm">
					{#each d.earnings as e}
						<li class="flex items-baseline gap-2 border-b border-line py-2 last:border-0">
							<span class="flex-1">{e.name}{#if e.hours}<span class="text-xs text-muted">&nbsp;· {e.hours.toLocaleString()} hrs</span>{/if}</span>
							<span class="w-14 text-right text-xs text-muted">{pct(e.amount)}</span>
							<span class="num w-24 text-right font-semibold">{money(e.amount, false)}</span>
						</li>
					{/each}
				</ul>
				{#if d.rate}
					<p class="mt-3 text-sm text-ink-2">
						Current rate: <span class="num font-semibold text-ink">{money(d.rate.hourly)}</span>/hr{#if d.rate.overtime}, overtime <span class="num">{money(d.rate.overtime)}</span>/hr{/if}{#if d.rate.salary}, <span class="num">{money(d.rate.salary, false)}</span> a year base{/if}.
						{#if d.rate.retirement_percent}You put {d.rate.retirement_percent}% toward retirement savings.{/if}
					</p>
				{/if}
				{#if d.employer.total}
					<details class="mt-4 rounded-lg bg-surface-2 p-3 text-sm">
						<summary class="flex items-baseline justify-between">
							<span>Your employer also paid</span>
							<span class="num font-semibold">{money(d.employer.total, false)}</span>
						</summary>
						<ul class="mt-2 text-ink-2">
							{#each d.employer.items as it}
								<li class="flex py-0.5"><span class="flex-1">{it.name}</span><span class="num">{money(it.amount)}</span></li>
							{/each}
						</ul>
						<p class="mt-2 text-xs text-muted">Benefits and contributions on top of your gross pay. Not in your paycheck, but part of what you're paid.</p>
					</details>
				{/if}
			</section>
		</div>

		<!-- By month -->
		<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
		<section class="card relative mt-4 overflow-x-auto" aria-labelledby="by-month" tabindex="0">
			<h2 class="label px-5 pt-5" id="by-month">By month</h2>
			<table class="mt-2 w-full text-sm">
				<thead>
					<tr class="border-b border-line text-left text-xs text-muted">
						<th scope="col" class="px-5 py-2 font-medium">Month</th>
						<th scope="col" class="px-3 py-2 text-right font-medium">Paychecks</th>
						<th scope="col" class="px-3 py-2 text-right font-medium">Gross</th>
						<th scope="col" class="px-5 py-2 text-right font-medium">Take-home</th>
					</tr>
				</thead>
				<tbody>
					{#each d.months as m}
						<tr class="border-b border-line last:border-0">
							<th scope="row" class="px-5 py-2 text-left font-normal">{monthName(m.month)}</th>
							<td class="px-3 py-2 text-right {m.checks > 2 ? 'font-semibold' : 'text-muted'}">{m.checks}</td>
							<td class="num px-3 py-2 text-right">{money(m.gross)}</td>
							<td class="num px-5 py-2 text-right font-semibold">{money(m.net)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</section>
	{/if}

	<!-- Leave -->
	{#if d.leave}
		{@const lv = d.leave}
		<section class="card mt-4 p-5">
			<div class="flex flex-wrap items-baseline justify-between gap-2">
				<h2 class="label">Leave</h2>
				<span class="text-xs text-muted">As of the pay period ending {dateLong(lv.as_of)}</span>
			</div>
			<div class="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
				{#each lv.kinds as k}
					<div class="rounded-lg bg-surface-2 p-3">
						<h3 class="text-sm font-semibold">{k.name}</h3>
						{#if k.balance !== null}
							<div class="num mt-1 text-xl font-semibold">{hours(k.balance)}</div>
							<div class="text-xs text-muted">{days(k.balance)} available</div>
						{:else}
							<div class="mt-1 text-xl font-semibold text-muted">—</div>
						{/if}
						<dl class="mt-2 grid grid-cols-[1fr_auto] gap-x-2 text-xs text-ink-2">
							{#if k.earned_per_period}<dt>Earned per pay period</dt><dd class="num text-right">{hours(k.earned_per_period)}</dd>{/if}
							{#if k.earned_ytd}<dt>Earned this leave year</dt><dd class="num text-right">{hours(k.earned_ytd)}</dd>{/if}
							{#if k.used_ytd}<dt>Used this leave year</dt><dd class="num text-right">{hours(k.used_ytd)}</dd>{/if}
							{#if k.expires}<dt>Expires</dt><dd class="text-right">{dateLong(k.expires)}</dd>{/if}
						</dl>
					</div>
				{/each}
			</div>
			{#if lv.projected !== undefined}
				<p class="mt-3 text-sm text-ink-2">
					Take no vacation before the leave year ends {dateLong(lv.year_end)} ({lv.periods_left} pay periods) and you'll have about
					<span class="font-semibold text-ink">{hours(lv.projected)} ({days(lv.projected)})</span>.
					{#if lv.use_or_lose}
						<span class="font-semibold text-warn-ink">{hours(lv.use_or_lose)} of that is over the {hours(lv.carryover_cap)} carryover limit: use it or lose it.</span>
					{:else if lv.carryover_cap}
						That's under the {hours(lv.carryover_cap)} you can carry over, so nothing is lost.
					{/if}
				</p>
			{/if}
			{#if leaveSeries.length && lv.history.length > 1}
				<div class="mt-4"><LeaveChart history={lv.history} series={leaveSeries} /></div>
				<div class="mt-1 flex flex-wrap gap-x-3 text-xs text-ink-2 sm:hidden">
					{#each leaveSeries as s}<span class="flex items-center gap-1.5"><span class="inline-block size-2.5 rounded-sm" aria-hidden="true" style="background:{s.color}"></span>{s.label}</span>{/each}
				</div>
			{/if}
		</section>
	{/if}

	<!-- Other money in -->
	{#if otherGroups.length}
		<section class="card mt-4 p-5">
			<h2 class="label">Other money in, {d.year}</h2>
			<p class="mt-1 text-xs text-muted">Deposits that aren't paychecks, from your bank data.</p>
			<div class="mt-3 grid gap-4 md:grid-cols-2">
				{#each otherGroups as g}
					<div>
						<div class="flex items-baseline justify-between text-sm font-semibold">
							<span>{g.k}</span><span class="num">{money(g.rows.reduce((s: number, r: any) => s + r.amount, 0), false)}</span>
						</div>
						<ul class="mt-1 text-sm">
							{#each g.rows as r}
								<li class="flex items-baseline gap-2 border-b border-line py-1.5 last:border-0">
									<span class="min-w-0 flex-1 truncate" title={r.name}>{r.name}</span>
									<span class="text-xs text-muted"><span class="sr-only">times:</span>{r.count}×</span>
									<span class="num w-20 text-right">{money(r.amount, r.amount < 10)}</span>
								</li>
							{/each}
						</ul>
					</div>
				{/each}
			</div>
			<p class="mt-3 text-xs text-muted">"Paid back" is money people sent you for shared costs (like rent and dinners), so it isn't really income.</p>
		</section>
	{/if}
{:else if !err}
	<p class="mt-3 text-sm text-muted" role="status">Loading…</p>
{/if}
