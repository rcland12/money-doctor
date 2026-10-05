<script lang="ts">
	/** A value you'll paste into a Shortcut, with a copy button. */
	let { value }: { value: string } = $props();
	let copied = $state(false);
	async function copy() {
		await navigator.clipboard.writeText(value);
		copied = true;
		setTimeout(() => (copied = false), 1500);
	}
</script>

<span class="inline-flex max-w-full items-start gap-1.5 rounded-md border border-line bg-surface-2 py-0.5 pr-1 pl-2 align-middle">
	<code class="min-w-0 py-0.5 text-[13px] break-all">{value}</code>
	<button class="shrink-0 rounded px-1.5 py-0.5 text-xs font-medium text-accent-ink" onclick={copy} aria-label="Copy {value}">{copied ? 'Copied' : 'Copy'}</button>
	<span class="sr-only" role="status">{copied ? 'Copied' : ''}</span>
</span>
