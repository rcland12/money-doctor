<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import { post } from '$lib/api.svelte';

	type Info = { file: string; kind: string; label: string; account: string | null; how: string | null; choices: { key: string; name: string }[]; ok: boolean };
	type Item = { file: File; info: Info | null; pick: string };

	let items: Item[] = $state([]);
	let checking = $state(false);
	let busy = $state(false);
	let result: any = $state(null);
	let error = $state('');
	let over = $state(false);

	async function pick(list: FileList | null) {
		if (!list?.length) return;
		const added: Item[] = Array.from(list).map((file) => ({ file, info: null, pick: '' }));
		items = [...items, ...added];
		result = null;
		error = '';
		checking = true;
		// Ask the server what each file is before anything is saved.
		const form = new FormData();
		for (const a of added) form.append('files', a.file);
		try {
			const infos: Info[] = await post('/v1/documents/inspect', form);
			for (const a of added) {
				const it = items.find((x) => x.file === a.file);
				if (it) it.info = infos.find((i) => i.file === a.file.name) ?? null;
			}
		} catch (e) {
			error = (e as Error).message;
		}
		checking = false;
	}

	const needsPick = (it: Item) => !!it.info && !it.info.account && it.info.choices.length > 0;
	const unusable = (it: Item) => it.info?.kind === 'unknown';
	const ready = $derived(items.length > 0 && !checking && items.every((it) => it.info && !unusable(it) && (!needsPick(it) || it.pick)));

	async function send() {
		busy = true;
		error = '';
		const form = new FormData();
		const accounts: Record<string, string> = {};
		for (const it of items) {
			form.append('files', it.file);
			if (needsPick(it)) accounts[it.file.name] = it.pick;
		}
		form.append('accounts', JSON.stringify(accounts));
		try {
			result = await post('/v1/documents', form);
			items = [];
		} catch (e) {
			error = (e as Error).message;
		}
		busy = false;
	}
</script>

<h1 class="text-xl font-semibold">Upload documents</h1>
<p class="mt-1 text-sm text-muted">
	Drop in anything from the bank or payroll: pay statements, card statements, and CSV exports for checking, savings or either card. Money Doctor
	works out what each file is and which account it belongs to. It only asks when it can't tell. Re-uploading is safe.
</p>

<label
	class="card mt-4 flex cursor-pointer flex-col items-center justify-center gap-2 border-dashed p-6 text-center focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent sm:p-10 {over ? 'bg-surface-2' : ''}"
	ondragover={(e) => (e.preventDefault(), (over = true))}
	ondragleave={() => (over = false)}
	ondrop={(e) => (e.preventDefault(), (over = false), pick(e.dataTransfer?.files ?? null))}
>
	<Icon name="upload" size={28} class="text-muted" />
	<span class="font-medium">Drop files here or tap to choose</span>
	<span class="text-xs text-muted">PDF, CSV or Excel</span>
	<input type="file" multiple class="sr-only" accept=".pdf,.csv,.xlsx" onchange={(e) => pick((e.target as HTMLInputElement).files)} />
</label>

{#if items.length}
	<ul class="card mt-3 divide-y divide-line text-sm" aria-label="Files to upload" aria-busy={checking}>
		{#each items as it, i}
			<li class="px-4 py-3">
				<div class="flex items-start gap-3">
					<div class="min-w-0 flex-1">
						<div class="truncate font-medium" title={it.file.name}>{it.file.name}</div>
						{#if !it.info}
							<div class="text-xs text-muted" role="status">Checking what this is…</div>
						{:else if unusable(it)}
							<div class="text-xs text-bad-ink"><Icon name="x" size={12} /> {it.info.label}. It will be skipped.</div>
						{:else if it.info.account || !it.info.choices.length}
							<div class="text-xs text-good-ink"><Icon name="check" size={12} /> {it.info.label}{it.info.how ? ` · ${it.info.how}` : ''}</div>
						{:else}
							<div class="text-xs text-warn-ink"><Icon name="alert" size={12} /> {it.info.label}: couldn't tell which account. Pick it:</div>
							<select bind:value={it.pick} class="mt-1.5 text-sm" aria-label="Account for {it.file.name}">
								<option value="">Choose…</option>
								{#each it.info.choices as c}<option value={c.key}>{c.name}</option>{/each}
							</select>
						{/if}
					</div>
					<button class="-m-2 grid min-h-11 min-w-11 shrink-0 place-items-center text-muted" onclick={() => items.splice(i, 1)} aria-label="Remove {it.file.name}"><Icon name="x" /></button>
				</div>
			</li>
		{/each}
	</ul>
	<button class="btn mt-3" disabled={!ready || busy} onclick={send}>
		{busy ? 'Reading…' : checking ? 'Checking files…' : `Upload ${items.length} file${items.length === 1 ? '' : 's'}`}
	</button>
{/if}

{#if error}<p class="mt-3 text-sm text-bad-ink" role="alert">{error}</p>{/if}
{#if result}
	<div class="card mt-3 p-4 text-sm" role="status">
		<p class="font-medium">{result.message}</p>
		<ul class="mt-2 space-y-0.5 text-xs text-muted">
			{#each result.saved as s}<li><Icon name="check" size={12} class="text-good-ink" /> {s.file} → {s.label}</li>{/each}
		</ul>
	</div>
{/if}
