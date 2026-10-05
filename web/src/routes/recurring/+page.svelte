<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { api } from '$lib/api.svelte';
	import { money, day } from '$lib/format';

	let data: any = $state(null);
	let freq = $state('all');
	let show = $state('current');
	let method = $state('');
	let sort = $state('frequency');

	api('/v1/recurring').then((r) => (data = r));

	const FREQ: Record<string, string> = { monthly: 'Monthly', semiannual: 'Every 6 months', yearly: 'Yearly', every_3_years: 'Every 3 years' };
	const FREQ_ORDER = ['monthly', 'semiannual', 'yearly', 'every_3_years'];
	const TYPE: Record<string, string> = {
		rent: 'Rent',
		loan: 'Loan',
		card_minimum: 'Card payment',
		bill: 'Bill',
		household: 'Household bill',
		subscription: 'Subscription'
	};
	const STATUS: Record<string, { label: string; role: string }> = {
		active: { label: 'Active', role: 'good' },
		ending: { label: 'Ending', role: 'muted' },
		decide: { label: 'Decide', role: 'warn' },
		cancelled: { label: 'Cancelled', role: 'muted' }
	};

	const methods = $derived(data ? [...new Set<string>(data.items.map((i: any) => i.method))].sort() : []);
	const rows = $derived.by(() => {
		if (!data) return [];
		let r = data.items.filter(
			(i: any) =>
				(freq === 'all' || i.frequency === freq) &&
				(show === 'all' || (show === 'current' ? i.status !== 'cancelled' : show === 'change' ? i.change && i.status !== 'cancelled' : i.status === show)) &&
				(!method || i.method === method)
		);
		const by: Record<string, (a: any, b: any) => number> = {
			frequency: (a, b) => FREQ_ORDER.indexOf(a.frequency) - FREQ_ORDER.indexOf(b.frequency) || (a.next ?? '9').localeCompare(b.next ?? '9'),
			next: (a, b) => (a.next ?? '9').localeCompare(b.next ?? '9'),
			amount: (a, b) => b.amount - a.amount,
			per_month: (a, b) => b.per_month - a.per_month,
			name: (a, b) => a.name.localeCompare(b.name)
		};
		return [...r].sort(by[sort]);
	});
	const shownMonthly = $derived(rows.filter((i: any) => i.status !== 'cancelled').reduce((s: number, i: any) => s + i.per_month, 0));

	function groupStart(i: number) {
		return sort === 'frequency' && (i === 0 || rows[i - 1].frequency !== rows[i].frequency);
	}
	function when(i: any) {
		if (i.status === 'cancelled') return 'Stopped';
		if (!i.next) return i.frequency === 'monthly' && i.day ? `The ${ordinal(i.day)}` : 'Date not set';
		return day(i.next, data.today);
	}
	function ordinal(n: number) {
		const s = ['th', 'st', 'nd', 'rd'];
		const v = n % 100;
		return n + (s[(v - 20) % 10] || s[v] || s[0]);
	}
	function daysAway(iso: string | null) {
		if (!iso) return null;
		return Math.round((new Date(iso + 'T12:00:00').getTime() - Date.now()) / 86400000);
	}
</script>

<div class="flex flex-wrap items-center justify-between gap-3">
	<h1 class="text-xl font-semibold">Recurring payments</h1>
</div>

{#if data}
	<div class="mt-3 grid gap-3 sm:grid-cols-3">
		<div class="card p-4">
			<div class="label">Per month, on average</div>
			<div class="num mt-1 text-2xl font-semibold">{money(data.per_month)}</div>
			<div class="text-xs text-muted">Yearly and 6-month items spread over 12 or 6 months</div>
		</div>
		<div class="card p-4">
			<div class="label">Per year</div>
			<div class="num mt-1 text-2xl font-semibold">{money(data.per_year, false)}</div>
			<div class="text-xs text-muted">Everything still active, rent and loans included</div>
		</div>
		<button class="card p-4 text-left" aria-pressed={show === 'change'} onclick={() => (show = show === 'change' ? 'current' : 'change')}>
			<div class="label">Worth switching</div>
			<div class="num mt-1 text-2xl font-semibold">{data.to_change}</div>
			<div class="text-xs text-muted">{show === 'change' ? 'Showing only these. Select to show all' : 'Paid a way we recommend changing. Select to see them'}</div>
		</button>
	</div>

	<div class="mt-4 flex flex-wrap items-center gap-2">
		<div class="flex flex-wrap gap-1 rounded-lg border border-line p-0.5 text-sm" role="group" aria-label="How often">
			{#each [['all', 'All'], ...FREQ_ORDER.filter((f) => data.items.some((i: any) => i.frequency === f)).map((f) => [f, FREQ[f]])] as [k, label]}
				<button class="min-h-11 rounded-md px-2.5 py-1 sm:min-h-0 {freq === k ? 'bg-surface-2 font-semibold text-ink' : 'text-ink-2'}" aria-pressed={freq === k} onclick={() => (freq = k)}>{label}</button>
			{/each}
		</div>
		<select bind:value={show} aria-label="Status">
			<option value="current">Active and ending</option>
			<option value="decide">Needs a decision</option>
			<option value="change">Worth switching</option>
			<option value="cancelled">Cancelled</option>
			<option value="all">Everything</option>
		</select>
		<select bind:value={method} aria-label="Paid with">
			<option value="">Any payment method</option>
			{#each methods as m}<option value={m}>{m}</option>{/each}
		</select>
		<label class="ml-auto flex items-center gap-2 text-sm text-muted">
			Sort
			<select bind:value={sort}>
				<option value="frequency">How often</option>
				<option value="next">Next date</option>
				<option value="amount">Amount</option>
				<option value="per_month">Cost per month</option>
				<option value="name">Name</option>
			</select>
		</label>
	</div>

	<p class="mt-2 text-sm text-muted" role="status">
		{rows.length} shown · <span class="num">{money(shownMonthly)}</span> a month on average
	</p>

	<div class="mt-2 grid gap-2">
		{#each rows as i, n (i.key)}
			{#if groupStart(n)}
				<h2 class="label mt-3 first:mt-0">{FREQ[i.frequency]}</h2>
			{/if}
			{@const st = STATUS[i.status] ?? STATUS.active}
			{@const away = daysAway(i.next)}
			<details class="card group {i.status === 'cancelled' ? 'border-dashed' : ''}">
				<summary class="grid list-none grid-cols-[1fr_auto] gap-x-4 gap-y-1 p-4 sm:grid-cols-[minmax(0,1.6fr)_7rem_8rem_minmax(0,1.4fr)_1rem] sm:items-center">
					<div class="min-w-0">
						<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
							<span class="font-semibold">{i.name}</span>
							{#if i.status !== 'active'}
								<span class="rounded-full px-2 py-0.5 text-xs font-medium
									{st.role === 'warn' ? 'bg-warn/15 text-warn-ink' : 'bg-surface-2 text-ink-2'}">{st.label}</span>
							{/if}
							{#if i.autopay}<span class="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-2">Autopay</span>{/if}
						</div>
						<div class="text-xs text-muted">{TYPE[i.type]}{i.line && i.line !== i.name ? ` · ${i.line}` : ''}</div>
					</div>
					<div class="text-right sm:order-none">
						<div class="num font-semibold">{money(i.amount)}</div>
						<div class="num text-xs text-muted">{i.frequency === 'monthly' ? FREQ[i.frequency].toLowerCase() : `${money(i.per_month)}/mo`}</div>
					</div>
					<div class="text-sm sm:text-left">
						<div class={away !== null && away <= 7 && i.status !== 'cancelled' ? 'font-semibold' : ''}>{when(i)}</div>
						{#if i.ends && i.status === 'ending'}<div class="text-xs text-muted">Last: {day(i.ends)}</div>
						{:else if away !== null && away > 7 && i.frequency !== 'monthly'}<div class="text-xs text-muted">in {away} days</div>{/if}
					</div>
					<div class="col-span-2 min-w-0 text-sm sm:col-span-1">
						{#if i.change}
							<div class="flex flex-wrap items-center gap-1.5">
								<span class="sr-only">Paid with</span>
								<span class="text-muted line-through decoration-1">{i.method}</span>
								<Icon name="right" />
								<span class="sr-only">, switch to</span>
								<span class="font-semibold text-accent-ink">{i.recommended}</span>
							</div>
						{:else}
							<div class="flex items-center gap-1.5"><span class="text-good-ink"><Icon name="check" /></span><span class="sr-only">Paid with</span>{i.method}</div>
						{/if}
					</div>
					<span class="hidden text-muted transition-transform group-open:rotate-90 sm:block"><Icon name="right" /></span>
				</summary>
				<div class="grid gap-2 border-t border-line px-4 py-3 text-sm text-ink-2">
					<p><span class="font-semibold text-ink">How to pay it:</span> {i.recommended}. {i.why}</p>
					{#if i.amount_note}<p><span class="font-semibold text-ink">Price:</span> {i.amount_note}</p>{/if}
					{#if i.note}<p>{i.note}</p>{/if}
					{#if i.next}<p class="text-muted">Next charge {day(i.next)}{i.frequency !== 'monthly' ? `, then every ${FREQ[i.frequency].toLowerCase().replace('every ', '').replace('yearly', 'year')}` : ', then every month'}.</p>{/if}
				</div>
			</details>
		{/each}
		{#if rows.length === 0}<p class="card p-4 text-sm text-muted">Nothing matches these filters.</p>{/if}
	</div>

	<p class="mt-4 text-xs text-muted">
		{#if data.cards_owed}
			While the cards carry a balance, fixed bills go on checking or the debit card: a card charge starts interest the day it posts. Once
			the cards are at $0, move them back to a rewards card and pay it in full every month.
		{:else}
			Your cards are at $0: put bills on a rewards card and pay the full statement every month.
		{/if}
		Add or edit these in the <code>recurring:</code> section of your budget file, then reload it from Settings.
	</p>
{:else}
	<p class="mt-3 text-sm text-muted" role="status">Loading…</p>
{/if}
