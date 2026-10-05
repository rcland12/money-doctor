<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { api, post, del } from '$lib/api.svelte';
	import { money, day, monthName, paceOf } from '$lib/format';
	import Meter from '$lib/components/Meter.svelte';

	let d: any = $state(null);
	let err = $state('');
	const load = () => api('/v1/dashboard').then((r) => (d = r)).catch((e) => (err = e.message));
	$effect(() => {
		load();
	});

	const groups = $derived(
		d ? [...new Set(d.lines.map((l: any) => l.group))].map((g) => ({ g, lines: d.lines.filter((l: any) => l.group === g) })) : []
	);
	const cards = $derived(d ? d.debts.filter((x: any) => x.kind === 'credit_card') : []);
	const cardsTotal = $derived(cards.reduce((s: number, c: any) => s + c.balance, 0));
	const cardsStart = $derived(cards.reduce((s: number, c: any) => s + (c.history[0]?.balance ?? c.balance), 0));

	async function markPaid(key: string, date: string) {
		await post(`/v1/bills/${encodeURIComponent(key)}/paid?month=${date.slice(0, 7)}`);
		load();
	}

	let sending = $state(false);
	let sent = $state({ account: '', amount: '', date: '' });
	let sentMsg = $state('');
	function openSent() {
		sending = !sending;
		sentMsg = '';
		const top = cards.find((c: any) => c.name === d.cash.send_to) ?? cards[0];
		sent = { account: top?.account ?? '', amount: '', date: d.today };
	}
	async function markSent(e: SubmitEvent) {
		e.preventDefault();
		const r: any = await post('/v1/card-payments', { account: sent.account, amount: Number(sent.amount), date: sent.date });
		sentMsg = r.message;
		sending = false;
		load();
	}
	async function undoSent(id: number) {
		await del(`/v1/transactions/${id}`);
		sentMsg = '';
		load();
	}

	const payDays = $derived.by(() => {
		if (!d) return [];
		const groups: { date: string; items: any[] }[] = [];
		for (const p of d.payments) {
			if (!groups.length || groups[groups.length - 1].date !== p.date) groups.push({ date: p.date, items: [] });
			groups[groups.length - 1].items.push(p);
		}
		return groups;
	});
</script>

<h1 class="sr-only">Today</h1>
{#if err}<p class="text-bad-ink" role="alert">{err}</p>{/if}
{#if d}
	<div class="grid gap-4 md:grid-cols-[1.4fr_1fr]">
		<!-- Safe to spend -->
		<section class="card p-5">
			<h2 class="label">Safe to spend today</h2>
			<div class="num mt-1 text-5xl font-bold tracking-tight">{money(d.safe.total_per_day)}</div>
			<p class="mt-1 text-sm text-muted">
				{money(d.safe.left_this_month)} left for {monthName(d.month).split(' ')[0]} across your everyday lines · {d.safe.days_left} days to go.
				A pace, not a limit: unspent money carries forward, and what's left at month end goes to your card payment.
			</p>
			<div class="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
				{#each d.safe.lines as l}
					<div>
						<div class="text-sm text-ink-2">{l.name}</div>
						<div class="num text-sm">
							{#if l.remaining <= 0}<span class="text-muted">used up</span>
							{:else}<span class="font-semibold">{money(l.per_day)}</span><span class="text-muted">/day</span>{/if}
						</div>
					</div>
				{/each}
			</div>
		</section>

		<!-- Payments -->
		<section class="card p-5">
			<h2 class="label">Payments</h2>
			{#if payDays.length === 0}<p class="mt-3 text-sm text-muted">Nothing to pay in the next two weeks.</p>{/if}
			{#each payDays as g}
				<div class="mt-3 text-xs font-bold tracking-wide uppercase {g.date === d.today ? 'text-accent-ink' : 'text-muted'}">
					{day(g.date, d.today)}{g.date === d.today ? ' · to do' : ''}
				</div>
				<ul class="divide-y divide-line">
					{#each g.items as p}
						<li class="py-2 text-sm">
							<div class="flex items-baseline gap-2">
								<span class="min-w-0 flex-1 font-medium">
									{p.name}
									{#if p.kind === 'bill'}<span class="text-xs font-normal text-muted"> from checking</span>{/if}
								</span>
								<span class="num font-semibold">{money(p.amount)}</span>
							</div>
							{#if p.parts.length}
								<details class="mt-0.5 text-xs text-muted">
									<summary class="cursor-pointer">What's in it</summary>
									<ul class="mt-1 space-y-0.5 pl-3">
										{#each p.parts as part}<li class="flex justify-between gap-3"><span>{part.label}</span><span class="num">{money(part.amount)}</span></li>{/each}
									</ul>
									{#if p.provisional}<p class="mt-1 italic">So far; it grows with new charges on the card.</p>{/if}
								</details>
							{/if}
							{#if p.note}<p class="mt-0.5 text-xs text-muted">{p.note}</p>{/if}
							<div class="mt-1">
								{#if p.paid}<span class="text-xs text-good-ink"><Icon name="check" size={12} /> Done</span>
								{:else if p.key}<button class="-my-1 py-1 text-xs text-accent-ink" aria-label="Mark {p.name} done" onclick={() => markPaid(p.key, p.date)}>Mark done</button>{/if}
							</div>
						</li>
					{/each}
				</ul>
			{/each}
		</section>
	</div>

	<div class="mt-4 grid gap-4 md:grid-cols-[1.4fr_1fr]">
		<!-- This month -->
		<section class="card p-5">
			<div class="flex items-baseline justify-between">
				<h2 class="label">{monthName(d.month)}</h2>
				<a href="/budget" class="text-sm text-accent-ink">Full budget <span aria-hidden="true">→</span></a>
			</div>
			{#each groups as { g, lines }}
				{@const shown = lines.filter((l: any) => l.kind === 'variable' && l.target > 0)}
				{#if shown.length}
					<h3 class="mt-4 text-sm font-semibold text-ink-2">{g}</h3>
					{#each shown as l}
						{@const p = paceOf(l)}
						<div class="mt-2">
							<div class="flex items-baseline justify-between text-sm">
								<span>{l.name}</span>
								<span class="num text-ink-2">{money(l.spent, false)} <span class="text-muted">of {money(l.target, false)}</span></span>
							</div>
							<div class="mt-1"><Meter value={l.spent} max={l.target} role={p?.role} label={l.name} /></div>
							{#if p && p.role !== 'good'}<div class="mt-0.5 text-xs" style="color:var(--{p.role}-ink)"><Icon name="dot" size={10} /> {p.label}</div>{/if}
						</div>
					{/each}
				{/if}
			{/each}
			{#if d.lines.find((l: any) => l.private && l.spent > 0)}
				{@const pl = d.lines.find((l: any) => l.private)}
				<p class="mt-4 text-sm text-warn-ink"><Icon name="dot" size={10} /> Personal: {money(pl.spent)} this month (goal $0)</p>
			{/if}
		</section>

		<div class="flex flex-col gap-4">
			<!-- Send early -->
			{#if d.cash && d.cash.balance !== null}
				<section class="card p-5">
					<div class="flex items-baseline justify-between">
						<h2 class="label">Pay cards early</h2>
						<a href="/calendar" class="text-sm text-accent-ink">Calendar <span aria-hidden="true">→</span></a>
					</div>
					<div class="num mt-1 text-2xl font-semibold">{money(d.cash.safe_to_send, false)}</div>
					<p class="mt-1 text-sm text-muted">
						{#if d.cash.safe_to_send > 0}
							How much of {d.cash.send_to}'s upcoming payments you can pay today and keep checking above {money(d.cash.cushion, false)}. It comes off the next scheduled payments; it isn't extra.
						{:else}
							Not today: checking is projected to dip to {money(d.cash.lowest.balance, false)} on {day(d.cash.lowest.date)}.
						{/if}
					</p>
					{#if d.cash.marked?.length}
						<ul class="mt-3 border-t border-line pt-2 text-sm">
							{#each d.cash.marked as m (m.id)}
								<li class="flex items-center gap-2 py-1">
									<span class="text-good-ink"><Icon name="check" /></span>
									<span class="flex-1">Sent <span class="num font-semibold">{money(m.amount)}</span> to {m.card} {day(m.date, d.today).toLowerCase()}
										<span class="block text-xs text-muted">Counted. Waiting for the bank to show it</span></span>
									<button class="-my-1 px-2 py-2 text-xs text-muted" aria-label="Undo {money(m.amount)} sent to {m.card}" onclick={() => undoSent(m.id)}>Undo</button>
								</li>
							{/each}
						</ul>
					{/if}
					<p class="text-sm text-good-ink {sentMsg ? 'mt-2' : ''}" role="status">{sentMsg}</p>
					{#if sending}
						<form id="sent-form" class="mt-3 grid gap-2 border-t border-line pt-3 text-sm" onsubmit={markSent}>
							<div class="grid grid-cols-[1fr_1fr] gap-2">
								<label class="grid gap-1 text-xs text-muted">Amount
									<input type="number" inputmode="decimal" step="0.01" min="0.01" required bind:value={sent.amount} placeholder="0.00" class="num text-sm" />
								</label>
								<label class="grid gap-1 text-xs text-muted">Card
									<select bind:value={sent.account} class="text-sm">
										{#each cards as c}<option value={c.account}>{c.name}</option>{/each}
									</select>
								</label>
							</div>
							<label class="grid gap-1 text-xs text-muted">Sent on
								<input type="date" bind:value={sent.date} max={d.today} required class="text-sm" />
							</label>
							<div class="flex gap-2">
								<button class="btn">Mark sent</button>
								<button type="button" class="btn-quiet" onclick={() => (sending = false)}>Cancel</button>
							</div>
						</form>
					{:else}
						<button class="btn-quiet mt-3 text-sm" aria-expanded="false" aria-controls="sent-form" onclick={openSent}>I sent a card payment</button>
					{/if}
				</section>
			{/if}

			<!-- Debt -->
			<section class="card p-5">
				<div class="flex items-baseline justify-between">
					<h2 class="label">Credit cards</h2>
					<a href="/debt" class="text-sm text-accent-ink">Payoff plan <span aria-hidden="true">→</span></a>
				</div>
				<div class="num mt-1 text-2xl font-semibold">{money(cardsTotal)}</div>
				<div class="mt-2"><Meter value={cardsStart - cardsTotal} max={cardsStart} role="good" label="Paid off since the plan started" /></div>
				<p class="mt-1 text-xs text-muted">{((1 - cardsTotal / cardsStart) * 100).toFixed(1)}% paid off since the plan started</p>
				{#if d.projection.done}
					<p class="mt-3 text-sm {d.projection.on_track ? 'text-good-ink' : 'text-bad-ink'}">
						<Icon name={d.projection.on_track ? 'check' : 'alert'} /> {d.projection.on_track ? 'On track' : 'Behind'}: paid off {monthName(d.projection.done)}
						<span class="text-muted">(target {monthName(d.projection.target)})</span>
					</p>
				{/if}
			</section>

			<!-- Coming up -->
			{#if d.events.length}
				<section class="card p-5">
					<h2 class="label">Coming up</h2>
					<ul class="mt-2 text-sm">
						{#each d.events.slice(0, 6) as e}
							<li class="flex gap-3 py-1">
								<span class="w-16 shrink-0 text-muted">{day(e.date, d.today)}</span>
								<span class="flex-1">{e.name}</span>
								{#if e.amount}<span class="num">{money(e.amount, false)}</span>{/if}
							</li>
						{/each}
					</ul>
				</section>
			{/if}
		</div>
	</div>

	<p class="mt-5 text-xs text-muted">
		Bank data through {d.freshness.bank_data_through ? day(d.freshness.bank_data_through) : '—'} · {d.freshness.logged_since} purchase{d.freshness
			.logged_since === 1
			? ''
			: 's'} logged since. <a href="/upload" class="text-accent-ink">Upload statements</a>
	</p>
{/if}
