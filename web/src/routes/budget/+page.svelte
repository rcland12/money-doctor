<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { api } from '$lib/api.svelte';
	import { money, monthName, shiftMonth, paceOf, day } from '$lib/format';
	import Meter from '$lib/components/Meter.svelte';

	let month = $state('');
	let b: any = $state(null);
	$effect(() => {
		api(`/v1/budget${month ? `?month=${month}` : ''}`).then((r) => {
			b = r;
			if (!month) month = r.month;
		});
	});
	const groups = $derived(
		b ? [...new Set(b.lines.map((l: any) => l.group))].map((g) => ({ g, lines: b.lines.filter((l: any) => l.group === g) })) : []
	);
	const total = $derived(b ? b.lines.reduce((s: number, l: any) => s + l.target, 0) + Math.max(0, b.cards_extra) : 0);
	const kindLabel: Record<string, string> = { variable: 'Everyday', bill: 'Bill', fund: 'Fund', savings: 'Savings' };
</script>

{#if b}
	<div class="flex flex-wrap items-center justify-between gap-3">
		<h1 class="text-xl font-semibold">{monthName(b.month)}</h1>
		<div class="flex gap-2">
			<button class="btn-quiet" onclick={() => (month = shiftMonth(b.month, -1))} aria-label="Previous month"><Icon name="left" /></button>
			<button class="btn-quiet" onclick={() => (month = shiftMonth(b.month, 1))} aria-label="Next month"><Icon name="right" /></button>
		</div>
	</div>
	<p class="mt-1 text-sm text-muted">
		Budgeted on two paychecks: <span class="num">{money(b.income.paycheck_net * b.income.budget_paychecks)}</span>. Everything not assigned
		below goes to the cards:
		<span class="num font-semibold text-accent-ink">{money(b.cards_extra)}</span> extra this month.
	</p>

	<div class="mt-4 flex flex-col gap-4">
		{#each groups as { g, lines }, gi}
			<section class="card p-4" aria-labelledby="group-{gi}">
				<h2 class="label" id="group-{gi}">{g}</h2>
				<div class="mt-2 divide-y divide-line">
					{#each lines as l}
						{@const p = paceOf(l)}
						<div class="py-2.5">
							<div class="flex flex-wrap items-baseline justify-between gap-x-4 text-sm">
								<span class="font-medium">{l.name} <span class="ml-1 text-xs font-normal text-muted">{kindLabel[l.kind]}</span></span>
								<span class="num text-ink-2">
									{money(l.spent)} <span class="text-muted">of {money(l.target)}</span>
								</span>
							</div>
							{#if l.target > 0}
								<div class="mt-1.5">
									<Meter value={l.spent} max={l.target} role={p?.role ?? (l.kind === 'bill' ? (l.paid ? 'good' : 'accent') : 'accent')} label={l.name} />
								</div>
							{/if}
							<div class="mt-1 flex flex-wrap gap-x-4 text-xs text-muted">
								{#if p}<span style="color:var(--{p.role}-ink)"><Icon name="dot" size={10} /> {p.label}</span>{/if}
								{#if l.kind === 'variable'}<span class="num">{money(l.remaining)} left</span>{/if}
								{#if l.due}<span>due {day(l.due)} · {#if l.paid}<span class="text-good-ink"><Icon name="check" size={12} /> paid</span>{:else}not paid yet{/if}</span>{/if}
								{#if l.balance !== undefined}<span class="num">fund balance {money(l.balance)}</span>{/if}
								{#if l.note}<span>{l.note}</span>{/if}
							</div>
						</div>
					{/each}
				</div>
			</section>
		{/each}
		<section class="card flex items-baseline justify-between p-4 text-sm">
			<h2 class="font-medium">Extra to the cards</h2><span class="num font-semibold text-accent-ink">{money(b.cards_extra)}</span>
		</section>
		<p class="text-xs text-muted">Total assigned: <span class="num">{money(total)}</span>. Edit the plan in <code>data/budget.yaml</code>, then Settings → Reload.</p>
	</div>
{/if}
