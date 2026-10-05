<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { api, patch, del, post } from '$lib/api.svelte';
	import { money, monthName, shiftMonth, day } from '$lib/format';

	let month = $state('');
	let line = $state('');
	let q = $state('');
	let data: any = $state(null);
	let adding = $state(false);
	let form = $state({ date: new Date().toISOString().slice(0, 10), amount: '', description: '', line: '' });

	function load() {
		const p = new URLSearchParams();
		if (month) p.set('month', month);
		if (line) p.set('line', line);
		if (q) p.set('q', q);
		api(`/v1/transactions?${p}`).then((r) => {
			data = r;
			if (!month) month = r.month;
		});
	}
	$effect(() => {
		month;
		line;
		load();
	});

	// Spending only: card/loan payments, transfers and investing move money but aren't spent.
	const notSpending = ['debt_payment', 'transfer_internal', 'investing', 'income', 'reimbursement'];
	const total = $derived(
		data ? data.transactions.reduce((s: number, t: any) => s + (t.amount < 0 && !notSpending.includes(t.category) ? -t.amount : 0), 0) : 0
	);

	async function setLine(t: any, value: string) {
		const name = data.lines.find((l: any) => l.key === value)?.name;
		const remember = !!value && confirm(`Always put "${t.description}" in ${name}?\n\nOK = every future one too · Cancel = just this one`);
		await patch(`/v1/transactions/${t.id}`, { line: value, remember });
		load();
	}
	async function remove(t: any) {
		await del(`/v1/transactions/${t.id}`);
		load();
	}
	async function add(e: SubmitEvent) {
		e.preventDefault();
		await post('/v1/transactions', { ...form, amount: -Math.abs(Number(form.amount)), line: form.line || null });
		adding = false;
		form.amount = '';
		form.description = '';
		load();
	}
</script>

{#if data}
	<div class="flex flex-wrap items-center justify-between gap-3">
		<h1 class="text-xl font-semibold">{monthName(data.month)}</h1>
		<div class="flex gap-2">
			<button class="btn-quiet" onclick={() => (month = shiftMonth(data.month, -1))} aria-label="Previous month"><Icon name="left" /></button>
			<button class="btn-quiet" onclick={() => (month = shiftMonth(data.month, 1))} aria-label="Next month"><Icon name="right" /></button>
			<button class="btn" onclick={() => (adding = !adding)} aria-expanded={adding} aria-controls="add-tx">Add</button>
		</div>
	</div>

	{#if adding}
		<form id="add-tx" class="card mt-3 grid gap-2 p-4 sm:grid-cols-[auto_auto_1fr_auto_auto]" onsubmit={add} aria-label="Add a transaction">
			<input type="date" bind:value={form.date} required aria-label="Date" />
			<input type="number" step="0.01" min="0" inputmode="decimal" placeholder="Amount" bind:value={form.amount} required class="sm:w-28" aria-label="Amount" />
			<input placeholder="What was it?" bind:value={form.description} required aria-label="Description" />
			<select bind:value={form.line} aria-label="Budget line">
				<option value="">No line</option>
				{#each data.lines as l}<option value={l.key}>{l.name}</option>{/each}
			</select>
			<button class="btn">Save</button>
		</form>
	{/if}

	<div class="mt-3 flex flex-wrap gap-2">
		<select bind:value={line} aria-label="Filter by line">
			<option value="">All lines</option>
			{#each data.lines as l}<option value={l.key}>{l.name}</option>{/each}
		</select>
		<form
			role="search"
			onsubmit={(e) => {
				e.preventDefault();
				load();
			}}
		>
			<input type="search" placeholder="Search" bind:value={q} aria-label="Search transactions" />
		</form>
		<span class="ml-auto self-center text-sm text-muted" aria-live="polite">Spent: <span class="num font-semibold text-ink">{money(total)}</span></span>
	</div>

	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<div class="card relative mt-3 overflow-x-auto" role="region" aria-label="Transactions" tabindex="0">
		<table class="w-full text-sm">
			<caption class="sr-only">Transactions for {monthName(data.month)}</caption>
			<thead>
				<tr class="border-b border-line text-left text-xs text-muted">
					<th scope="col" class="px-3 py-2 font-medium">Date</th>
					<th scope="col" class="px-3 py-2 font-medium">Description</th>
					<th scope="col" class="px-3 py-2 font-medium">Line</th>
					<th scope="col" class="px-3 py-2 text-right font-medium">Amount</th>
					<th scope="col"><span class="sr-only">Actions</span></th>
				</tr>
			</thead>
			<tbody>
				{#each data.transactions as t (t.id)}
					<tr class="border-b border-line last:border-0">
						<td class="px-3 py-2 whitespace-nowrap text-muted">{day(t.date)}</td>
						<td class="max-w-[22rem] px-3 py-2">
							<div class="truncate" title={t.description}>{t.description}</div>
							<div class="text-xs text-muted">
								{t.account ?? ''}{t.source !== 'import' ? ` · ${t.source}` : ''}{t.note && t.note !== t.description ? ` · ${t.note}` : ''}
							</div>
						</td>
						<td class="px-3 py-2">
							<select class="max-w-40 text-xs" aria-label="Line for {t.description}" value={t.pinned ? t.line : ''} onchange={(e) => setLine(t, (e.target as HTMLSelectElement).value)}>
								<option value="">{t.line_name ? `${t.line_name} (auto)` : '—'}</option>
								{#each data.lines as l}<option value={l.key}>{l.name}</option>{/each}
							</select>
						</td>
						<td class="num px-3 py-2 text-right whitespace-nowrap {t.amount > 0 ? 'text-good-ink' : ''}">{money(t.amount)}</td>
						<td class="px-2">
							{#if t.source !== 'import'}<button class="grid min-h-11 min-w-11 place-items-center text-xs text-muted sm:min-h-8 sm:min-w-8" onclick={() => remove(t)} title="Delete" aria-label="Delete {t.description}"><Icon name="x" /></button>{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{#if data.transactions.length === 0}<p class="p-4 text-sm text-muted">No transactions.</p>{/if}
	</div>
{/if}
