<script lang="ts">
	/** One calendar day in detail: what to pay, what charges on its own, what's already done,
	 * money in, and balances. A modal <dialog> (a bottom sheet on phones). */
	import { money } from '$lib/format';
	import Icon from './Icon.svelte';

	type Part = { label: string; amount: number };
	type Flow = { name: string; amount: number; kind?: string; account?: string | null; note?: string | null; parts?: Part[]; autopay?: boolean };
	export type Day = {
		date: string;
		in: Flow[];
		out: Flow[];
		done: Flow[];
		auto: Flow[];
		spend: number;
		start: number | null;
		end: number | null;
		payday: boolean;
	};
	type Account = { name: string; balance: number; as_of?: string | null; kind?: string; limit?: number | null; source?: string };

	let {
		day,
		today,
		cushion,
		lowest,
		accounts,
		hasPrev,
		hasNext,
		onprev,
		onnext,
		onclose
	}: {
		day: Day | null;
		today: string;
		cushion: number;
		lowest: { date: string; balance: number } | null;
		accounts: { cash: Account[]; investments: Account[]; debts: Account[] } | null;
		hasPrev: boolean;
		hasNext: boolean;
		onprev: () => void;
		onnext: () => void;
		onclose: () => void;
	} = $props();

	let dialog: HTMLDialogElement | undefined = $state();
	$effect(() => {
		if (!dialog) return;
		if (day && !dialog.open) dialog.showModal();
		if (!day && dialog.open) dialog.close();
	});

	const long = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
	const short = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	const sum = (xs: Flow[]) => xs.reduce((s, x) => s + x.amount, 0);
	const from = (x: Flow) =>
		x.kind === 'transfer' ? 'From checking' : x.kind === 'card' ? `From checking to ${x.account ?? 'the card'}` : x.account ? `On ${x.account}` : 'From checking';

	const toPay = $derived(day ? day.out.filter((x) => !x.autopay) : []);
	const automatic = $derived(day ? [...day.out.filter((x) => x.autopay), ...day.auto] : []);
	const isToday = $derived(day?.date === today);

	function keydown(e: KeyboardEvent) {
		if (e.key === 'ArrowLeft' && hasPrev) onprev();
		if (e.key === 'ArrowRight' && hasNext) onnext();
	}
</script>

{#snippet flow(x: Flow, sign: string, note = true)}
	<li class="py-2.5">
		<div class="flex items-baseline justify-between gap-3">
			<span class="min-w-0 font-medium break-words">{x.name}</span>
			<span class="num shrink-0 font-semibold">{sign}{money(x.amount)}</span>
		</div>
		{#if x.kind || x.account}<div class="text-xs text-muted">{from(x)}{x.autopay ? ', autopay' : ''}</div>{/if}
		{#if x.parts?.length}
			<ul class="mt-1 space-y-0.5 text-xs text-ink-2">
				{#each x.parts as p}
					<li class="flex justify-between gap-3"><span class="min-w-0">{p.label}</span><span class="num shrink-0">{money(p.amount)}</span></li>
				{/each}
			</ul>
		{/if}
		{#if note && x.note}<p class="mt-1 text-xs text-muted">{x.note}</p>{/if}
	</li>
{/snippet}

{#snippet accountList(title: string, xs: Account[], owed = false)}
	{#if xs.length}
		<h4 class="mt-3 text-xs font-semibold text-muted">{title}</h4>
		<ul class="divide-y divide-line text-sm">
			{#each xs as a}
				<li class="flex items-baseline justify-between gap-3 py-1.5">
					<span class="min-w-0 break-words">
						{a.name}{#if a.as_of}<span class="text-xs text-muted">, as of {short(a.as_of)}</span>{/if}
					</span>
					<span class="num shrink-0">
						{money(a.balance)}
						{#if owed && a.limit}<span class="block text-right text-xs text-muted">{Math.round((a.balance / a.limit) * 100)}% of limit</span>{/if}
					</span>
				</li>
			{/each}
		</ul>
	{/if}
{/snippet}

<dialog
	bind:this={dialog}
	aria-labelledby="day-title"
	class="day-sheet m-0 mt-auto max-h-[88dvh] w-full max-w-none overflow-hidden rounded-t-2xl border border-line bg-surface p-0 text-ink sm:m-auto sm:max-h-[85vh] sm:max-w-lg sm:rounded-2xl"
	onclose={onclose}
	onkeydown={keydown}
	onclick={(e) => e.target === dialog && onclose()}
>
	{#if day}
		<div class="flex max-h-[inherit] flex-col">
			<header class="flex items-center gap-2 border-b border-line px-4 py-3">
				<button type="button" class="icon-btn" aria-label="Previous day" disabled={!hasPrev} onclick={onprev}><Icon name="left" size={18} /></button>
				<div class="min-w-0 flex-1 text-center">
					<h2 id="day-title" class="font-semibold">{long(day.date)}</h2>
					<p class="text-xs text-muted">
						{[isToday && 'Today', day.payday && 'Payday', day.date === lowest?.date && 'Lowest point'].filter(Boolean).join(', ') || 'Checking forecast'}
					</p>
				</div>
				<button type="button" class="icon-btn" aria-label="Next day" disabled={!hasNext} onclick={onnext}><Icon name="right" size={18} /></button>
				<button type="button" class="icon-btn" aria-label="Close" onclick={onclose}><Icon name="x" size={18} /></button>
			</header>

			<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
			<div tabindex="0" role="region" aria-label="Day details" class="overflow-y-auto overscroll-contain px-4 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))]">
				<section aria-labelledby="day-checking">
					<h3 id="day-checking" class="label">Checking</h3>
					{#if day.end === null}
						<p class="mt-1 text-sm text-muted">Connect bank sync to see a projected balance.</p>
					{:else}
						<dl class="mt-1 grid grid-cols-2 gap-2 text-sm">
							<div class="rounded-lg bg-surface-2 p-2.5">
								<dt class="text-xs text-muted">{isToday ? 'Available now' : 'Start of day'}</dt>
								<dd class="num text-lg font-semibold">{money(day.start)}</dd>
							</div>
							<div class="rounded-lg bg-surface-2 p-2.5">
								<dt class="text-xs text-muted">End of day (projected)</dt>
								<dd class="num text-lg font-semibold {day.end < cushion ? 'text-bad-ink' : ''}">{money(day.end)}</dd>
							</div>
						</dl>
						{#if day.end < cushion}
							<p class="mt-2 flex items-start gap-1.5 text-sm text-bad-ink">
								<Icon name="alert" class="mt-0.5" /> Below your {money(cushion, false)} cushion.
							</p>
						{/if}
					{/if}
				</section>

				{#if day.in.length}
					<section aria-labelledby="day-in" class="mt-4">
						<h3 id="day-in" class="label">Money in</h3>
						<ul class="divide-y divide-line text-sm">
							{#each day.in as x}{@render flow(x, '+')}{/each}
						</ul>
					</section>
				{/if}

				<section aria-labelledby="day-pay" class="mt-4">
					<h3 id="day-pay" class="label">Payments to make{toPay.length ? `: ${money(sum(toPay))}` : ''}</h3>
					{#if toPay.length}
						<ul class="divide-y divide-line text-sm">
							{#each toPay as x}{@render flow(x, '−')}{/each}
						</ul>
					{:else}
						<p class="mt-1 text-sm text-muted">Nothing to send by hand.</p>
					{/if}
				</section>

				{#if automatic.length}
					<section aria-labelledby="day-auto" class="mt-4">
						<h3 id="day-auto" class="label">Charges on their own</h3>
						<p class="text-xs text-muted">Autopay and subscriptions. No action needed, just make sure the money is there.</p>
						<ul class="divide-y divide-line text-sm">
							{#each automatic as x}{@render flow(x, '−')}{/each}
						</ul>
					</section>
				{/if}

				{#if day.done.length}
					<section aria-labelledby="day-done" class="mt-4">
						<h3 id="day-done" class="label">Already paid</h3>
						<ul class="divide-y divide-line text-sm">
							{#each day.done as x}
								<li class="flex items-baseline justify-between gap-3 py-2">
									<span class="flex min-w-0 items-baseline gap-1.5 text-ink-2"><Icon name="check" class="text-good-ink" />{x.name}</span>
									<span class="num shrink-0 text-ink-2">{money(x.amount)}</span>
								</li>
							{/each}
						</ul>
					</section>
				{/if}

				<p class="mt-4 text-sm text-ink-2">
					Everyday spending at budget pace: <span class="num font-medium">{money(day.spend)}</span>
				</p>

				{#if accounts}
					<section aria-labelledby="day-bal" class="mt-4 border-t border-line pt-3">
						<h3 id="day-bal" class="label">{isToday ? 'Balances now' : 'Balances (latest known)'}</h3>
						{#if !isToday}<p class="text-xs text-muted">Checking above is projected for this day; these are the last synced or entered balances.</p>{/if}
						{@render accountList('Cash', accounts.cash)}
						{@render accountList('Cards and loans', accounts.debts, true)}
						{@render accountList('Investments', accounts.investments)}
					</section>
				{/if}
			</div>
		</div>
	{/if}
</dialog>

<style>
	.day-sheet::backdrop {
		background: rgb(0 0 0 / 0.45);
	}
	:global(html:has(dialog.day-sheet[open])) {
		overflow: hidden;
	}
	.icon-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		border-radius: 10px;
		color: var(--ink-2);
		flex-shrink: 0;
	}
	.icon-btn:hover:not(:disabled) {
		background: var(--surface-2);
	}
</style>
