<script lang="ts">
	/** A thin progress bar. The caller always shows the numbers as text too. */
	let { value, max, role = 'accent', label = '' }: { value: number; max: number; role?: string; label?: string } = $props();
	const frac = $derived(max > 0 ? Math.min(Math.max(value / max, 0), 1) : 0);
</script>

<div
	class="h-1.5 w-full overflow-hidden rounded-full bg-surface-2"
	role="meter"
	aria-valuenow={Math.round(value)}
	aria-valuemin="0"
	aria-valuemax={Math.round(max)}
	aria-label={label}
	aria-valuetext="{Math.round(value).toLocaleString('en-US')} of {Math.round(max).toLocaleString('en-US')}"
>
	<div class="h-full rounded-full transition-[width]" style="width:{frac * 100}%;background:var(--{role})"></div>
</div>
