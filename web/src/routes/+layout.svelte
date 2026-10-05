<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { api, auth, post } from '$lib/api.svelte';

	let { children } = $props();
	let password = $state('');
	let error = $state('');

	const nav = [
		['/', 'Today'],
		['/calendar', 'Calendar'],
		['/recurring', 'Recurring'],
		['/budget', 'Budget'],
		['/transactions', 'Transactions'],
		['/debt', 'Debt'],
		['/income', 'Income'],
		['/upload', 'Upload'],
		['/settings', 'Settings']
	];
	const title = $derived(page.url.pathname === '/setup' ? 'Setup' : (nav.find(([href]) => href === page.url.pathname)?.[1] ?? ''));

	$effect(() => {
		if (!auth.checked)
			api('/auth/me').then((r) => {
				auth.user = r.user;
				auth.mode = r.mode;
				auth.checked = true;
			});
	});

	async function login(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		try {
			await post('/auth/login', { password });
			auth.user = 'owner';
		} catch (err) {
			error = (err as Error).message;
		}
	}
</script>

<svelte:head><title>{title && title !== 'Today' ? `${title} · Money Doctor` : 'Money Doctor'}</title></svelte:head>

{#if !auth.checked}
	<div class="p-8 text-muted" role="status">Loading…</div>
{:else if !auth.user}
	<main class="mx-auto mt-24 max-w-sm px-4">
		<form class="card flex flex-col gap-3 p-6" onsubmit={login}>
			<h1 class="text-xl font-semibold">Money Doctor</h1>
			<label for="password" class="sr-only">Password</label>
			<input id="password" type="password" placeholder="Password" bind:value={password} autocomplete="current-password" required />
			{#if error}<p class="text-sm text-bad-ink" role="alert">{error}</p>{/if}
			<button class="btn">Log in</button>
		</form>
	</main>
{:else}
	<a
		href="#main"
		class="sr-only z-20 rounded-lg bg-surface px-3 py-2 font-semibold focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:border focus:border-line"
		>Skip to main content</a
	>
	<header class="sticky top-0 z-10 border-b border-line bg-bg/90 pt-[env(safe-area-inset-top)] backdrop-blur">
		<div class="mx-auto flex max-w-5xl items-center gap-4 py-1.5 pr-[max(1rem,env(safe-area-inset-right))] pl-[max(1rem,env(safe-area-inset-left))]">
			<a href="/" class="flex min-h-11 shrink-0 items-center gap-2 font-semibold" aria-label="Money Doctor, home">
				<img src="/favicon.svg" alt="" class="h-6 w-6" /> <span class="hidden sm:inline" aria-hidden="true">Money Doctor</span>
			</a>
			<nav aria-label="Main" class="-mx-1 flex min-w-0 gap-1 overflow-x-auto px-1 py-1 text-sm">
				{#each nav as [href, label]}
					<a
						{href}
						aria-current={page.url.pathname === href ? 'page' : undefined}
						class="flex min-h-11 shrink-0 items-center rounded-lg px-2.5 sm:min-h-9 {page.url.pathname === href
							? 'bg-surface-2 font-semibold text-ink'
							: 'text-ink-2'}">{label}</a
					>
				{/each}
			</nav>
		</div>
	</header>
	<main id="main" tabindex="-1" class="mx-auto max-w-5xl px-4 py-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
		{@render children()}
	</main>
{/if}
