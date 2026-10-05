<script lang="ts">
	import { api } from '$lib/api.svelte';
	import { money } from '$lib/format';
	import BalanceChart from '$lib/components/BalanceChart.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import DayDetail, { type Day } from '$lib/components/DayDetail.svelte';

	type Flow = { name: string; amount: number };
	let f: any = $state(null);
	let open: number | null = $state(null); // index into f.days
	let opener: HTMLElement | null = null;
	function show(d: Day, e: Event) {
		opener = e.currentTarget as HTMLElement;
		open = (f.days as Day[]).indexOf(d);
	}
	function close() {
		open = null;
		opener?.focus();
	}
	$effect(() => {
		api('/v1/calendar?days=42').then((r) => (f = r));
	});

	const fmt = (iso: string, opts: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' }) =>
		new Date(iso + 'T12:00:00').toLocaleDateString('en-US', opts);
	const sum = (xs: Flow[]) => xs.reduce((s, x) => s + x.amount, 0);
	const busy = $derived(f ? (f.days as Day[]).filter((d) => d.in.length || d.out.length || d.done.length || d.auto.length) : []);
	const count = (d: Day) => d.out.length + d.auto.length;
	const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;
	function describe(d: Day) {
		const bits = [fmt(d.date, { weekday: 'long', month: 'long', day: 'numeric' })];
		if (d.date === f.today) bits.push('today');
		if (d.payday) bits.push('payday');
		if (d.date === f.lowest?.date) bits.push('lowest point');
		if (d.out.length) bits.push(`${plural(d.out.length, 'payment')}, ${money(sum(d.out), false)}`);
		if (d.auto.length) bits.push(plural(d.auto.length, 'automatic charge'));
		if (d.end !== null) bits.push(`checking ends at ${money(d.end, false)}${d.end < f.cushion ? ', below cushion' : ''}`);
		return bits.join(', ');
	}

	// Month-style grid: whole weeks, Sunday first, covering the forecast.
	const weeks = $derived.by(() => {
		if (!f) return [];
		const days: Day[] = f.days;
		const first = new Date(days[0].date + 'T12:00:00');
		const lead = first.getDay();
		const cells: (Day | null)[] = [...Array(lead).fill(null), ...days];
		while (cells.length % 7) cells.push(null);
		const out = [];
		for (let i = 0; i < cells.length; i += 7) out.push(cells.slice(i, i + 7));
		return out;
	});
</script>

<h1 class="text-xl font-semibold">Calendar</h1>
<p class="mt-1 text-sm text-muted">
	Checking, day by day: paychecks and roommates' shares in; bills, card payments, savings transfers and everyday spending (at budget pace) out.
</p>

{#if f}
	<div class="mt-4 grid gap-4 md:grid-cols-[1fr_1.4fr]">
		<section class="card min-w-0 p-5">
			<h2 class="label">Pay your cards early</h2>
			{#if f.balance === null}
				<p class="mt-2 text-sm text-muted">Connect bank sync to see this.</p>
			{:else if f.safe_to_send > 0}
				<div class="num mt-1 text-4xl font-bold tracking-tight">{money(f.safe_to_send, false)}</div>
				<p class="mt-2 text-sm">
					You can pay up to <strong>{money(f.safe_to_send, false)}</strong> of <strong>{f.send_to}</strong>'s upcoming payments today, and
					checking stays above your {money(f.cushion, false)} cushion.
				</p>
				<p class="mt-2 text-sm text-muted">
					It isn't extra: the card's next scheduled payments get smaller by the same amount, so the payoff date doesn't change. Paying sooner just
					saves a little interest. Checking's lowest point is {money(f.lowest.balance, false)} on {fmt(f.lowest.date)}.
				</p>
			{:else}
				<div class="num mt-1 text-4xl font-bold tracking-tight text-muted">$0</div>
				<p class="mt-2 text-sm">
					Not today. Checking is projected to get down to {money(f.lowest.balance, false)} on {fmt(f.lowest.date)}, which is at or under your
					{money(f.cushion, false)} cushion. Keep the scheduled payments only.
				</p>
			{/if}
			<p class="mt-3 border-t border-line pt-3 text-xs text-muted">
				Checking available: <span class="num">{money(f.balance)}</span>{f.as_of ? ` (bank sync, ${fmt(f.as_of, { month: 'short', day: 'numeric' })})` : ''}.
				Not counted until they arrive: overtime, and roommate shares for this month.
			</p>
		</section>

		<section class="card min-w-0 p-5">
			<h2 class="label">Checking, next six weeks</h2>
			<div class="mt-3"><BalanceChart days={f.days} cushion={f.cushion} lowest={f.lowest} /></div>
		</section>
	</div>

	<section class="card mt-4 p-2 sm:p-4" aria-labelledby="grid-title">
		<h2 id="grid-title" class="label px-1 pb-2">Next six weeks</h2>
		<div class="grid grid-cols-7 gap-0.5 text-center text-xs font-semibold text-muted sm:gap-1" aria-hidden="true">
			{#each ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as w}<div class="pb-1.5"><span class="sm:hidden">{w[0]}</span><span class="hidden sm:inline">{w}</span></div>{/each}
		</div>
		<ul class="grid grid-cols-7 gap-0.5 sm:gap-1" aria-label="Days. Choose a day for its payments and balances.">
			{#each weeks as week}
				{#each week as d}
					{#if d}
						{@const out = sum(d.out)}
						{@const n = count(d)}
						<li class="min-w-0">
							<button
								type="button"
								aria-label={describe(d)}
								aria-haspopup="dialog"
								onclick={(e) => show(d, e)}
								class="flex h-full min-h-14 w-full flex-col items-stretch rounded-lg border p-1 text-left text-xs hover:bg-surface-2 sm:min-h-24 sm:p-1.5 {d.date ===
								f.lowest?.date
									? 'border-2 border-warn'
									: d.date === f.today
										? 'border-2 border-accent'
										: 'border-line'} {d.payday ? 'bg-surface-2' : ''}"
							>
								<span class="flex items-baseline justify-between gap-0.5">
									<span class="font-semibold">{fmt(d.date, { day: 'numeric' })}</span>
									{#if new Date(d.date + 'T12:00:00').getDate() === 1 || d === f.days[0]}<span class="hidden text-muted sm:inline">{fmt(d.date, { month: 'short' })}</span>{/if}
								</span>
								<!-- Phones: short markers. Wider: the full summary. -->
								<span class="mt-0.5 flex flex-wrap gap-0.5 sm:hidden">
									{#if d.payday}<span class="font-semibold text-good-ink">$</span>{/if}
									{#if n}<span class="num text-ink-2">{n}</span>{/if}
									{#if d.date === f.lowest?.date}<Icon name="alert" size={11} class="text-warn-ink" />{/if}
								</span>
								<span class="hidden sm:block">
									{#if d.payday}<span class="mt-0.5 block font-medium text-good-ink">Payday</span>{/if}
									{#if d.date === f.lowest?.date}<span class="mt-0.5 block font-medium text-warn-ink">Lowest</span>{/if}
									{#if d.out.length}
										<span class="mt-0.5 block text-ink-2">{plural(d.out.length, 'payment')}</span>
										<span class="num block text-ink-2">−{money(out, false)}</span>
									{/if}
									{#if d.auto.length}<span class="block text-muted">{d.auto.length} automatic</span>{/if}
								</span>
								{#if d.end !== null}
									<span class="num mt-auto hidden pt-1 text-[11px] sm:block {d.end < f.cushion ? 'text-bad-ink' : 'text-muted'}">{money(d.end, false)}</span>
								{/if}
							</button>
						</li>
					{:else}
						<li aria-hidden="true"></li>
					{/if}
				{/each}
			{/each}
		</ul>
		<p class="mt-2 px-1 text-xs text-muted">
			Tap or click a day for everything on it: payments to make, autopay and subscriptions, and balances.
			<span class="sm:hidden">"$" marks a payday and the number counts payments and automatic charges.</span>
			<span class="hidden sm:inline">The small number is checking's projected balance at the end of the day.</span>
			The day outlined in yellow is checking's lowest point; today is outlined in blue.
		</p>
	</section>

	<!-- Day by day -->
	<section class="card mt-4 p-5">
		<h2 class="label" id="list-title">Day by day</h2>
		<ul class="mt-2 divide-y divide-line" aria-labelledby="list-title">
			{#each busy as d}
				<li>
					<button type="button" class="-mx-2 block w-[calc(100%+1rem)] rounded-lg px-2 py-3 text-left text-sm hover:bg-surface-2" aria-haspopup="dialog" onclick={(e) => show(d, e)}>
						<span class="flex flex-wrap items-baseline justify-between gap-x-3">
							<span class="flex items-center gap-1 font-semibold">{fmt(d.date)} <Icon name="right" size={12} class="text-muted" /></span>
							<span class="num text-xs {d.end !== null && d.end < f.cushion ? 'text-bad-ink' : 'text-muted'}">
								{#if d.date === f.lowest?.date}<Icon name="alert" size={12} /> lowest,{/if} ends at {money(d.end)}
							</span>
						</span>
						<span class="mt-1 block space-y-0.5">
							{#each d.in as x}<span class="flex justify-between gap-3 text-good-ink"><span class="min-w-0">{x.name}</span><span class="num shrink-0">+{money(x.amount)}</span></span>{/each}
							{#each d.out as x}<span class="flex justify-between gap-3"><span class="min-w-0">{x.name}{x.autopay ? ' (autopay)' : ''}</span><span class="num shrink-0">−{money(x.amount)}</span></span>{/each}
							{#each d.auto as x}<span class="flex justify-between gap-3 text-ink-2"><span class="min-w-0">{x.name} (automatic)</span><span class="num shrink-0">−{money(x.amount)}</span></span>{/each}
							{#each d.done as x}<span class="flex justify-between gap-3 text-muted"><span class="flex min-w-0 items-baseline gap-1"><Icon name="check" size={12} />{x.name} (paid)</span><span class="num shrink-0">{money(x.amount)}</span></span>{/each}
						</span>
					</button>
				</li>
			{/each}
		</ul>
		<p class="mt-2 text-xs text-muted">
			Every day also takes about {money(f.days[0]?.spend ?? 0)} of everyday spending (groceries, gas, dining, fun) at budget pace.
		</p>
	</section>
	<DayDetail
		day={open === null ? null : f.days[open]}
		today={f.today}
		cushion={f.cushion}
		lowest={f.lowest}
		accounts={f.accounts}
		hasPrev={open !== null && open > 0}
		hasNext={open !== null && open < f.days.length - 1}
		onprev={() => open !== null && open > 0 && open--}
		onnext={() => open !== null && open < f.days.length - 1 && open++}
		onclose={close}
	/>
{/if}
