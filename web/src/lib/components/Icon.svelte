<script lang="ts">
	/** Small line icons (Lucide-style, 24px grid) used for status and controls instead of emoji. */
	let { name, size = 14, class: cls = '' }: { name: 'check' | 'alert' | 'dot' | 'x' | 'left' | 'right' | 'upload'; size?: number; class?: string } = $props();
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width="2.25"
	stroke-linecap="round"
	stroke-linejoin="round"
	class="inline-block shrink-0 align-[-0.15em] {cls}"
	aria-hidden="true"
>
	{#if name === 'check'}<path d="M20 6 9 17l-5-5" />
	{:else if name === 'alert'}<path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
	{:else if name === 'dot'}<circle cx="12" cy="12" r="5" fill="currentColor" stroke="none" />
	{:else if name === 'x'}<path d="M18 6 6 18M6 6l12 12" />
	{:else if name === 'left'}<path d="m15 18-6-6 6-6" />
	{:else if name === 'right'}<path d="m9 18 6-6-6-6" />
	{:else if name === 'upload'}<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="m17 8-5-5-5 5" /><path d="M12 3v12" />
	{/if}
</svg>
