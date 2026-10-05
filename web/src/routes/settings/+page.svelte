<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { api, post, del, auth } from '$lib/api.svelte';

	let tokens: any[] = $state([]);
	let name = $state('iPhone');
	let fresh = $state('');
	let preview: any = $state(null);
	let msg = $state('');
	let sfin: any = $state(null);
	let sfinToken = $state('');
	let sfinBusy = $state(false);
	let sfinMsg = $state('');
	let accountKeys: { key: string; name: string }[] = $state([]);
	const loadSfin = () => api('/v1/simplefin').then((r) => (sfin = r));
	$effect(() => {
		loadSfin();
		api('/v1/accounts').then((r) => (accountKeys = r));
	});
	function syncText(r: any) {
		return `${r.added} new transaction${r.added === 1 ? '' : 's'}, ${r.already_had} already here${r.matched_to_logged ? `, ${r.matched_to_logged} matched to ones you logged` : ''}.`;
	}
	async function sfinConnect() {
		sfinBusy = true;
		sfinMsg = '';
		try {
			const r = await post('/v1/simplefin/claim', { token: sfinToken });
			sfinToken = '';
			sfinMsg = r.sync ? `Connected. First sync: ${syncText(r.sync)}` : `Connected. ${r.sync_error ?? ''}`;
		} catch (e) {
			sfinMsg = (e as Error).message;
		}
		sfinBusy = false;
		loadSfin();
	}
	async function sfinSync() {
		sfinBusy = true;
		try {
			sfinMsg = syncText(await post('/v1/simplefin/sync'));
		} catch (e) {
			sfinMsg = (e as Error).message;
		}
		sfinBusy = false;
		loadSfin();
	}
	async function sfinMap(id: string, key: string) {
		sfin = await post('/v1/simplefin/map', { account_id: id, key: key || null });
		sfinSync();
	}
	async function sfinDisconnect() {
		if (!confirm('Disconnect bank sync? You can reconnect later with a new setup token.')) return;
		sfin = await post('/v1/simplefin/disconnect');
	}
	let calUrl = $state('');
	let calCopied = $state(false);
	async function copyCal() {
		await navigator.clipboard.writeText(calUrl);
		calCopied = true;
		setTimeout(() => (calCopied = false), 1500);
	}
	$effect(() => {
		api('/v1/calendar/link').then((r) => (calUrl = r.url));
	});
	async function resetCal() {
		if (!confirm('Make a new calendar link? Calendars subscribed with the old one stop updating until you re-subscribe.')) return;
		calUrl = (await post('/v1/calendar/link/reset')).url;
	}
	let mailInfo: any = $state(null);
	let mailBusy = $state(false);
	const loadMail = () => api('/v1/mail').then((r) => (mailInfo = r));
	$effect(() => {
		loadMail();
	});
	async function checkMail() {
		mailBusy = true;
		try {
			const r = await post('/v1/mail/check');
			msg = `Email: ${r.logged} logged, ${r.review} to review${r.matched ? `, ${r.matched} matched to entries you logged` : ''}.`;
		} catch (e) {
			msg = (e as Error).message;
		}
		mailBusy = false;
		loadMail();
	}

	const loadTokens = () => api('/v1/tokens').then((r) => (tokens = r));
	$effect(() => {
		loadTokens();
	});

	async function create() {
		fresh = (await post('/v1/tokens', { name })).token;
		loadTokens();
	}
	async function revoke(id: number) {
		await del(`/v1/tokens/${id}`);
		loadTokens();
	}
	async function reload() {
		const r = await post('/v1/reload');
		msg = `Reloaded the budget. ${r.import.added} new transactions.`;
	}
	async function sendDigest() {
		msg = (await post('/v1/digest/send')).message;
	}
	async function logout() {
		await post('/auth/logout');
		auth.user = null;
	}
</script>

<h1 class="text-xl font-semibold">Settings</h1>

<section class="card mt-4 p-5">
	<h2 class="label">Shortcut tokens</h2>
	<p class="mt-1 text-sm text-muted">
		For Shortcuts that call this site directly. Behind an API gateway that adds its own token, the phone doesn't need one.
	</p>
	<div class="mt-3 flex flex-wrap gap-2">
		<label for="token-name" class="sr-only">Token name</label>
		<input id="token-name" bind:value={name} class="min-w-0 flex-1 sm:flex-none" />
		<button class="btn" onclick={create}>Create token</button>
	</div>
	{#if fresh}
		<div class="mt-3 rounded-lg bg-surface-2 p-3 text-sm" role="status">
			Copy this now; it won't be shown again:
			<code class="mt-1 block break-all select-all">{fresh}</code>
		</div>
	{/if}
	<ul class="mt-3 divide-y divide-line text-sm">
		{#each tokens as t}
			<li class="flex items-center justify-between gap-3 py-2">
				<span class="min-w-0">{t.name} <span class="text-xs text-muted">· last used {t.last_used ? new Date(t.last_used).toLocaleString() : 'never'}</span></span>
				<button class="min-h-11 shrink-0 px-2 text-xs text-bad-ink sm:min-h-0" onclick={() => revoke(t.id)} aria-label="Revoke {t.name}">Revoke</button>
			</li>
		{/each}
	</ul>
	<p class="mt-3"><a class="btn inline-block" href="/setup">iPhone setup guide <span aria-hidden="true">→</span></a></p>
</section>

<section class="card mt-4 p-5">
	<h2 class="label">Morning email</h2>
	<div class="mt-3 flex flex-wrap gap-2">
		<button class="btn-quiet" onclick={async () => (preview = await api('/v1/digest/preview'))}>Preview</button>
		<button class="btn-quiet" onclick={sendDigest}>Send now</button>
	</div>
	{#if preview}
		<p class="mt-3 text-sm font-medium">{preview.subject}</p>
		<iframe title="Email preview" srcdoc={preview.html} class="mt-2 h-[70vh] max-h-[640px] w-full rounded-lg border border-line bg-white"></iframe>
	{/if}
</section>

<section class="card mt-4 p-5">
	<h2 class="label">Calendar subscription</h2>
	<p class="mt-2 text-sm">
		Payments, paydays and reminders in your phone's calendar, with a 9:00 AM alert on payment days. It updates by itself as payments change.
	</p>
	{#if calUrl}
		<div class="mt-3 rounded-lg bg-surface-2 p-3 text-xs"><code class="break-all select-all">{calUrl}</code></div>
		<div class="mt-2 flex flex-wrap gap-2">
			<button class="btn-quiet" onclick={copyCal}>Copy link</button>
			<span class="self-center text-sm text-good-ink" role="status">{calCopied ? 'Copied' : ''}</span>
			<button class="btn-quiet" onclick={resetCal}>Reset link</button>
		</div>
	{/if}
	<div class="mt-3 grid gap-3 text-sm sm:grid-cols-2">
		<div>
			<h3 class="font-semibold">Apple Calendar (iPhone)</h3>
			<ol class="mt-1 list-decimal space-y-0.5 pl-5 text-ink-2">
				<li>Copy the link above.</li>
				<li>Settings → Apps → Calendar → Calendar Accounts → Add Account → Other.</li>
				<li>Add Subscribed Calendar → paste → Next → Save.</li>
			</ol>
		</div>
		<div>
			<h3 class="font-semibold">Google Calendar (on a computer)</h3>
			<ol class="mt-1 list-decimal space-y-0.5 pl-5 text-ink-2">
				<li>Other calendars → + → From URL.</li>
				<li>Paste the link → Add calendar.</li>
				<li>Google refreshes subscribed calendars slowly (up to a day), and doesn't use the alerts.</li>
			</ol>
		</div>
	</div>
	<p class="mt-3 text-xs text-muted">The link works without logging in, so treat it like a password. Reset it if it ever leaks.</p>
</section>

<section class="card mt-4 p-5">
	<h2 class="label">Bank sync (SimpleFIN)</h2>
	{#if sfin}
		{#if !sfin.connected}
			<p class="mt-2 text-sm">
				Pulls transactions and balances from your bank a few times a day, so you don't have to download CSVs. At
				<a class="text-accent-ink" href="https://beta-bridge.simplefin.org" target="_blank" rel="noreferrer">SimpleFIN Bridge<span class="sr-only"> (opens in a new tab)</span></a>, link your bank, then
				create a <strong>setup token</strong> and paste it here. It works once; Money Doctor trades it for its own private key.
			</p>
			<textarea class="mt-3 w-full font-mono text-xs" rows="3" placeholder="Paste the setup token" aria-label="SimpleFIN setup token" autocomplete="off" spellcheck="false" bind:value={sfinToken}></textarea>
			<button class="btn mt-2" disabled={sfinBusy || sfinToken.trim().length < 20} onclick={sfinConnect}>{sfinBusy ? 'Connecting…' : 'Connect'}</button>
		{:else}
			<p class="mt-2 text-sm">
				Connected. Syncs every 6 hours.
				{#if sfin.last_sync}<span class="text-muted">Last sync {new Date(sfin.last_sync).toLocaleString()}.</span>{/if}
			</p>
			{#if sfin.error}<p class="mt-1 text-sm text-bad-ink" role="alert"><Icon name="alert" /> {sfin.error}</p>{/if}
			{#each sfin.errors as e}<p class="mt-1 text-sm text-warn-ink"><Icon name="alert" /> SimpleFIN: {e}</p>{/each}
			{#if sfin.accounts.length}
				<ul class="mt-3 divide-y divide-line text-sm">
					{#each sfin.accounts as a}
						<li class="flex flex-wrap items-center gap-2 py-2">
							<span class="min-w-0 flex-1">
								{a.name} <span class="text-xs text-muted">{a.org ?? ''}</span>
							</span>
							<span class="num text-ink-2">{a.balance.toLocaleString('en-US', { style: 'currency', currency: 'USD' })}</span>
							{#if a.mapped_to}
								<span class="text-xs text-good-ink"><Icon name="check" size={12} /> {a.mapped_to.startsWith('debt:') ? 'balance only' : a.mapped_to.replace(/_/g, ' ')}</span>
							{:else}
								<select class="text-xs" aria-label="Use {a.name} as" onchange={(e) => sfinMap(a.id, (e.target as HTMLSelectElement).value)}>
									<option value="">Not used: pick an account…</option>
									{#each accountKeys as k}<option value={k.key}>{k.name}</option>{/each}
								</select>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
			<div class="mt-3 flex flex-wrap gap-2">
				<button class="btn-quiet" disabled={sfinBusy} onclick={sfinSync}>{sfinBusy ? 'Syncing…' : 'Sync now'}</button>
				<button class="btn-quiet" onclick={sfinDisconnect}>Disconnect</button>
			</div>
		{/if}
		<p class="mt-2 text-sm empty:hidden" role="status">{sfinMsg}</p>
	{/if}
</section>

<section class="card mt-4 p-5">
	<h2 class="label">Email receipts</h2>
	{#if mailInfo}
		{#if !mailInfo.configured}
			<p class="mt-2 text-sm text-muted">
				Not connected. Set <code>MAIL_USER</code> and <code>MAIL_PASSWORD</code> (a Gmail app password) and create a Gmail label called
				<strong>{mailInfo.folder}</strong>. See the <a class="text-accent-ink" href="/setup">setup guide</a>.
			</p>
		{:else}
			<p class="mt-2 text-sm">
				Reading the Gmail label <strong>{mailInfo.folder}</strong> every two minutes.
				{#if mailInfo.state.last_check}<span class="text-muted">Last check {new Date(mailInfo.state.last_check).toLocaleString()}.</span>{/if}
			</p>
			{#if mailInfo.state.error}<p class="mt-1 text-sm text-bad-ink" role="alert"><Icon name="alert" /> {mailInfo.state.error}</p>{/if}
			<button class="btn-quiet mt-3" disabled={mailBusy} onclick={checkMail}>{mailBusy ? 'Checking…' : 'Check now'}</button>
			{#if mailInfo.recent.length}
				<ul class="mt-3 divide-y divide-line text-sm">
					{#each mailInfo.recent as m}
						<li class="flex gap-3 py-1.5">
							<span class="w-14 shrink-0 text-muted">{m.date.slice(5)}</span>
							<span class="min-w-0 flex-1 truncate" title={m.subject}>{m.subject}</span>
							{#if m.status === 'logged'}<span class="shrink-0 text-xs text-good-ink"><Icon name="check" size={12} /> logged</span>
							{:else}<span class="shrink-0 text-xs text-warn-ink"><Icon name="alert" size={12} /> needs a look</span>{/if}
						</li>
					{/each}
				</ul>
				<p class="mt-2 text-xs text-muted">"Needs a look" means it looked like a payment but didn't match a known format. Nothing was logged for it.</p>
			{/if}
		{/if}
	{/if}
</section>

<section class="card mt-4 p-5">
	<h2 class="label">Budget</h2>
	<p class="mt-1 text-sm text-muted">After editing <code>data/budget.yaml</code> or the merchant rules, reload to apply them.</p>
	<button class="btn-quiet mt-3" onclick={reload}>Reload budget & re-import</button>
</section>

<p class="mt-3 text-sm empty:hidden" role="status">{msg}</p>
{#if auth.mode === 'password'}<button class="btn-quiet mt-6" onclick={logout}>Log out</button>
{:else if auth.mode === 'proxy'}<a class="btn-quiet mt-6 inline-block" href="/oauth2/sign_out?rd=/">Sign out</a>{/if}
