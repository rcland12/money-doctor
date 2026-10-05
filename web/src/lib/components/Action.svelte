<script lang="ts">
	import type { Snippet } from 'svelte';
	/** One action in a Shortcut: its number matches the line number in the Shortcuts app. */
	let { n, name, children }: { n: number | string; name: string; children?: Snippet } = $props();
</script>

<li class="flex gap-3 border-t border-line py-3 first:border-t-0">
	<span class="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-surface-2 text-xs font-bold text-ink-2">{n}</span>
	<div class="min-w-0 flex-1">
		<div class="font-semibold">{name}</div>
		{#if children}<div class="mt-1.5 space-y-2 text-sm text-ink-2">{@render children()}</div>{/if}
	</div>
</li>
