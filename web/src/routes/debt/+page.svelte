<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { api, post } from '$lib/api.svelte';
	import { money, monthName, day } from '$lib/format';
	import Meter from '$lib/components/Meter.svelte';
	import PayoffChart from '$lib/components/PayoffChart.svelte';

	let d: any = $state(null);
	let editing: string | null = $state(null);
	let value = $state('');
	const load = () => api('/v1/dashboard').then((r) => (d = r));
	$effect(() => {
		load();
	});

	let editingAsset: string | null = $state(null);
	let assetValue = $state('');
	async function saveAsset(key: string) {
		await post(`/v1/assets/${key}/balance`, { balance: Number(assetValue) });
		editingAsset = null;
		load();
	}

	async function save(key: string) {
		await post(`/v1/debts/${key}/balance`, { balance: Number(value) });
		editing = null;
		load();
	}
	const kinds: Record<string, string> = { credit_card: 'Credit card', auto: 'Auto loan', installment: 'Installment' };
</script>

{#if d}
	{@const p = d.projection}
	<h1 class="text-xl font-semibold">Debt payoff</h1>
	<section class="card mt-3 p-5">
		<div class="flex flex-wrap items-baseline justify-between gap-2">
			<h2 class="label">Projected credit card balance</h2>
			{#if p.done}
				<div class="text-sm {p.on_track ? 'text-good-ink' : 'text-bad-ink'}">
					<Icon name={p.on_track ? 'check' : 'alert'} /> {p.on_track ? 'On track' : 'Behind'}: paid off {monthName(p.done)} · target {monthName(p.target)}
				</div>
			{/if}
		</div>
		<div class="mt-3"><PayoffChart series={p.series} target={p.target} /></div>
		<p class="mt-2 text-sm text-muted">
			Avalanche: minimums on everything, every extra dollar to the highest rate first.
			Interest still to pay on this plan: <span class="num text-ink">{money(p.interest, false)}</span>.
			{#each Object.entries(p.paid_off) as [k, m]}
				{@const debt = d.debts.find((x: any) => x.key === k)}
				<span class="whitespace-nowrap">{debt?.name} done {monthName(m as string)}.</span>{' '}
			{/each}
		</p>
	</section>

	{@const nw = d.net_worth}
	<section class="card mt-4 p-5">
		<div class="flex flex-wrap items-baseline justify-between gap-2">
			<h2 class="label">Net worth</h2>
			<div class="num text-2xl font-semibold {nw.net < 0 ? 'text-ink' : 'text-good-ink'}">{money(nw.net, false)}</div>
		</div>
		<div class="mt-3 grid gap-6 sm:grid-cols-2">
			<div>
				<div class="flex justify-between text-sm font-semibold"><h3>What you have</h3><span class="num">{money(nw.total_assets, false)}</span></div>
				<ul class="mt-1 divide-y divide-line text-sm">
					{#each nw.assets as a}
						<li class="py-1.5">
							<div class="flex items-baseline justify-between gap-3">
								<span class="min-w-0">{a.name}</span>
								{#if editingAsset === a.key}
									<form class="flex gap-1" onsubmit={(e) => (e.preventDefault(), saveAsset(a.key))}>
										<input type="number" step="0.01" inputmode="decimal" bind:value={assetValue} class="w-28 text-sm" aria-label="{a.name} balance" />
										<button class="btn-quiet text-xs">Save</button>
									</form>
								{:else}
									<span class="num">{money(a.balance)}</span>
								{/if}
							</div>
							<div class="text-xs text-muted">
								{a.source === 'bank sync' ? 'from bank sync' : 'entered'}{a.as_of ? ` · ${day(a.as_of)}` : ''}
								{#if a.editable && editingAsset !== a.key}
									· <button class="text-accent-ink" onclick={() => ((editingAsset = a.key), (assetValue = String(a.balance)))} aria-label="Update {a.name}">Update</button>
								{/if}
							</div>
						</li>
					{/each}
				</ul>
			</div>
			<div>
				<div class="flex justify-between text-sm font-semibold"><h3>What you owe</h3><span class="num">{money(nw.total_debts, false)}</span></div>
				<ul class="mt-1 divide-y divide-line text-sm">
					{#each nw.debts as x}<li class="flex justify-between gap-3 py-1.5"><span class="min-w-0">{x.name}</span><span class="num">{money(x.balance)}</span></li>{/each}
				</ul>
			</div>
		</div>
	</section>

	<div class="mt-4 grid gap-4 md:grid-cols-2">
		{#each d.debts as x}
			<section class="card p-5">
				<div class="flex items-baseline justify-between gap-3">
					<div class="min-w-0">
						<h2 class="font-semibold">{x.name}</h2>
						<div class="text-xs text-muted">{kinds[x.kind] ?? x.kind} · {x.apr}% APR · minimum {money(x.minimum)}</div>
					</div>
					<button class="-my-2 min-h-11 shrink-0 px-2 text-xs text-accent-ink sm:min-h-0" onclick={() => ((editing = x.key), (value = String(x.balance)))} aria-label="Update {x.name} balance">Update</button>
				</div>
				{#if editing === x.key}
					<form class="mt-3 flex flex-wrap gap-2" onsubmit={(e) => (e.preventDefault(), save(x.key))}>
						<input type="number" step="0.01" inputmode="decimal" bind:value class="w-36" aria-label="{x.name} balance" />
						<button class="btn">Save</button>
						<button type="button" class="btn-quiet" onclick={() => (editing = null)}>Cancel</button>
					</form>
				{:else}
					<div class="num mt-2 text-3xl font-semibold">{money(x.balance)}</div>
					<div class="text-xs text-muted">as of {x.as_of ? day(x.as_of) : '—'}</div>
				{/if}
				{#if x.limit}
					<div class="mt-3"><Meter value={x.balance} max={x.limit} role={x.used > 0.9 ? 'bad' : x.used > 0.3 ? 'warn' : 'good'} label="{x.name} credit used" /></div>
					<div class="mt-1 text-xs text-muted">
						<span class="num">{Math.round(x.used * 100)}%</span> of the <span class="num">{money(x.limit, false)}</span> limit used
						{#if x.used > 0.3} · under 30% stops hurting your credit score{/if}
					</div>
				{/if}
				{#if x.history.length > 1}
					<div class="mt-3 text-xs text-muted">
						History: {#each x.history.slice(-4) as h, i}{#if i}<span aria-hidden="true"> → </span><span class="sr-only">, then </span>{/if}<span class="num">{money(h.balance, false)}</span>{/each}
					</div>
				{/if}
			</section>
		{/each}
	</div>
{/if}
