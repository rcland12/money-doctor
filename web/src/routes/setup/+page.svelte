<script lang="ts">
	import { api } from '$lib/api.svelte';
	import Copy from '$lib/components/Copy.svelte';
	import Action from '$lib/components/Action.svelte';

	let info = $state<{ base: string; auth: string; site: string } | null>(null);
	$effect(() => {
		api('/v1/setup').then((r) => (info = r));
	});
	const cf = $derived(info?.auth === 'cloudflare-access');
</script>

<!-- Reusable instruction blocks -->
{#snippet add(name: string)}
	<p>Tap the <strong>Search Actions</strong> bar at the bottom, type <strong>{name}</strong>, and tap it in the results.</p>
{/snippet}

{#snippet url(path: string)}
	<p>The action reads "Get contents of <span class="text-accent-ink">URL</span>". Tap the blue <strong>URL</strong> and paste:</p>
	<p><Copy value="{info?.base}{path}" /></p>
{/snippet}

{#snippet more()}
	<p>Tap the small <strong>›</strong> arrow on the right edge of the action. More options appear under it: <strong>Method</strong>, <strong>Headers</strong>, <strong>Request Body</strong>.</p>
{/snippet}

{#snippet method(m: string)}
	{#if m === 'GET'}
		<p>Leave <strong>Method</strong> as <strong>GET</strong>.</p>
	{:else}
		<p>Tap <strong>Method</strong> and choose <strong>{m}</strong>.</p>
	{/if}
{/snippet}

{#snippet headers()}
	{#if cf}
		<p>Tap <strong>Headers</strong>, then <strong>Add new header</strong>. Two boxes appear:</p>
		<ul class="list-disc space-y-1 pl-5">
			<li><strong>Key</strong>: type <code>CF-Access-Client-Id</code></li>
			<li><strong>Text</strong>: paste your service token's <strong>Client ID</strong> (it ends in <code>.access</code>)</li>
		</ul>
		<p>Tap <strong>Add new header</strong> again:</p>
		<ul class="list-disc space-y-1 pl-5">
			<li><strong>Key</strong>: type <code>CF-Access-Client-Secret</code></li>
			<li><strong>Text</strong>: paste the <strong>Client Secret</strong></li>
		</ul>
	{:else}
		<p>Tap <strong>Headers</strong>, then <strong>Add new header</strong>. <strong>Key</strong>: <code>Authorization</code>. <strong>Text</strong>: type <code>Bearer</code>, a space, then paste your token from Settings.</p>
	{/if}
{/snippet}

{#snippet message(n: number)}
	<Action {n} name="Get Dictionary Value">
		{@render add('Get Dictionary Value')}
		<p>It reads "Get <span class="text-accent-ink">Value</span> for <span class="text-accent-ink">Key</span> in <span class="text-accent-ink">Contents of URL</span>".</p>
		<p>Tap <strong>Key</strong> and type <code>message</code>. Leave the other two as they are.</p>
	</Action>
{/snippet}

{#snippet notify(n: number, kind = 'Show Notification')}
	<Action {n} name={kind}>
		{@render add(kind)}
		{#if kind === 'Show Notification'}
			<p>
				It usually fills in <span class="text-accent-ink">Dictionary Value</span> by itself. If it shows
				<span class="text-accent-ink">Hello World!</span> instead, tap it, delete the text, and tap <strong>Dictionary Value</strong> in the bar
				above the keyboard.
			</p>
		{:else}
			<p>
				It fills in <span class="text-accent-ink">Dictionary Value</span> by itself: the reply from Money Doctor. (On older iOS this action is
				called <em>Show Result</em>.)
			</p>
		{/if}
	</Action>
{/snippet}

{#snippet field(type: string, key: string)}
	<p>Tap <strong>Add new field</strong> and choose <strong>{type}</strong>. In <strong>Key</strong> type <code>{key}</code>.</p>
{/snippet}

{#snippet looks(lines: string[])}
	<div class="mt-4 rounded-lg bg-surface-2 p-3 text-sm">
		<div class="text-xs font-semibold text-muted">When you're done it should have {lines.length} lines</div>
		<ol class="mt-1.5 list-decimal space-y-0.5 pl-5">
			{#each lines as l}<li>{l}</li>{/each}
		</ol>
	</div>
{/snippet}

{#snippet title(n: number, text: string, time: string)}
	<div class="flex items-baseline gap-3">
		<span class="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[var(--btn)] text-sm font-bold text-white" aria-hidden="true">{n}</span>
		<h2 class="min-w-0 text-lg font-semibold"><span class="sr-only">Part {n}: </span>{text}</h2>
		<span class="ml-auto shrink-0 text-xs text-muted">{time}</span>
	</div>
{/snippet}

<div class="mx-auto max-w-2xl">
	<h1 class="text-2xl font-semibold">Set up your iPhone</h1>
	<p class="mt-1 text-ink-2">
		Nine parts, about 45 minutes the first time. Keep this page open on your phone and switch to the Shortcuts app as you go. Do them in
		order: each one reuses the one before.
	</p>

	{#if info}
		<!-- Basics -->
		<section class="card mt-4 p-5">
			<h2 class="label">Read this first: how the Shortcuts app works</h2>
			<ul class="mt-2 list-disc space-y-2 pl-5 text-sm">
				<li>A Shortcut is a list of <strong>actions</strong> that run top to bottom. The numbered steps below are those actions, in order: one step = one line in your Shortcut.</li>
				<li><strong>To add an action</strong>, tap the <strong>Search Actions</strong> bar at the bottom of the editor, type its name, and tap it. New actions go at the end of the list.</li>
				<li><strong>Blue words</strong> inside an action are boxes you tap to fill in.</li>
				<li>Some actions have a small <strong>›</strong> arrow on the right. Tap it to see more options.</li>
				<li>
					<strong>Variables</strong> are the blue bubbles that carry a result from one action to the next. When you tap a box, a bar appears above
					the keyboard with suggestions (like <em>Contents of URL</em>); tap one to insert it. If what you need isn't there, tap
					<strong>Select Variable</strong>, then tap the earlier action whose result you want.
				</li>
				<li>Made a mistake? Swipe an action left (or tap its ✕) to delete it, and drag actions by their icon to reorder.</li>
			</ul>
			<p class="mt-3 text-sm text-muted">Names can vary slightly between iOS versions (for example "Show More" instead of the › arrow). Look for the closest match.</p>
		</section>

		<section class="card mt-4 p-5">
			<h2 class="label">Before you start</h2>
			{#if cf}
				<p class="mt-2 text-sm">
					Have your Cloudflare Access <strong>service token</strong> handy: its <strong>Client ID</strong> and <strong>Client Secret</strong>. Every
					Shortcut sends them. Keep them in your password manager so you can copy and paste them.
				</p>
			{:else}
				<p class="mt-2 text-sm">Create a token in <a class="text-accent-ink" href="/settings">Settings</a> and keep it where you can copy it.</p>
			{/if}
		</section>

		<!-- 1: Home Screen -->
		<section class="card mt-4 p-5">
			{@render title(1, 'Put Money Doctor on your Home Screen', '1 min')}
			<ol class="mt-3">
				<Action n={1} name="Open the site in Safari">
					<p>Open <Copy value={info.site} /> in <strong>Safari</strong> (not Chrome) and log in.</p>
				</Action>
				<Action n={2} name="Add it to the Home Screen">
					<p>Tap the <strong>Share</strong> button (the square with an arrow), scroll down, tap <strong>Add to Home Screen</strong>, then <strong>Add</strong>.</p>
				</Action>
			</ol>
			<p class="mt-2 text-sm text-muted">It opens full screen like an app. You'll log in about once a week.</p>
		</section>

		<!-- 2: Money Today -->
		<section class="card mt-4 p-5">
			{@render title(2, 'Money Today', '5 min')}
			<p class="mt-2 text-sm text-ink-2">
				The simplest one, so build it first: it proves the connection works. Afterwards, "Hey Siri, money today" reads out what's safe to
				spend and what's due.
			</p>
			<p class="mt-3 text-sm">
				<strong>Create it:</strong> open <strong>Shortcuts</strong> → <strong>Shortcuts</strong> tab → <strong>+</strong> (top right). Tap the
				name at the top ("New Shortcut") → <strong>Rename</strong> → type <strong>Money Today</strong>.
			</p>
			<ol class="mt-2">
				<Action n={1} name="Get Contents of URL">
					{@render add('Get Contents of URL')}
					{@render url('/summary')}
					{@render more()}
					{@render method('GET')}
					{@render headers()}
				</Action>
				{@render message(2)}
				{@render notify(3, 'Show Content')}
			</ol>
			{@render looks(['Get contents of …/summary (GET, 2 headers)', 'Get Value for message in Contents of URL', 'Show Content: Dictionary Value'])}
			<p class="mt-3 text-sm"><strong>Test it:</strong> tap <strong>▶</strong> at the bottom. You should see today's safe-to-spend amount. If you get an error, check the headers before going on.</p>
		</section>

		<!-- 3: Undo Last -->
		<section class="card mt-4 p-5">
			{@render title(3, 'Undo Last', '2 min')}
			<p class="mt-2 text-sm text-ink-2">Removes the last purchase you logged from the phone, for when you type the wrong amount.</p>
			<p class="mt-3 text-sm">
				<strong>Create it by copying Money Today</strong>, so the headers come along: in the Shortcuts tab, long-press <strong>Money Today</strong> →
				<strong>Duplicate</strong>. Open the copy, tap its name → <strong>Rename</strong> → <strong>Undo Last</strong>. Then change:
			</p>
			<ol class="mt-2">
				<Action n={1} name="Get Contents of URL (change it)">
					<p>Tap the URL and replace it with <Copy value="{info.base}/undo" /></p>
					{@render more()}
					{@render method('POST')}
					<p>The headers are already there. Leave them.</p>
				</Action>
				<Action n={2} name="Get Dictionary Value (no change)" />
				<Action n={3} name="Replace Show Content with Show Notification">
					<p>Delete the <strong>Show Content</strong> action (swipe left or tap ✕).</p>
					{@render add('Show Notification')}
					<p>It usually fills in <strong>Dictionary Value</strong> by itself. If it shows <strong>Hello World!</strong>, tap it, delete it, and tap <strong>Dictionary Value</strong> above the keyboard.</p>
				</Action>
			</ol>
			{@render looks(['Get contents of …/undo (POST, 2 headers)', 'Get Value for message in Contents of URL', 'Show notification Dictionary Value'])}
		</section>

		<!-- 4: Log Expense -->
		<section class="card mt-4 p-5">
			{@render title(4, 'Log Expense', '8 min')}
			<p class="mt-2 text-sm text-ink-2">For cash, Zelle, Venmo, Cash App, PayPal, and physical card swipes. It asks what it was and how much.</p>
			<p class="mt-3 text-sm">
				<strong>Create it by copying Undo Last</strong> (long-press → <strong>Duplicate</strong>), rename it <strong>Log Expense</strong>, then
				delete actions <strong>2</strong> and <strong>3</strong> (keep the first one). Now build it like this:
			</p>
			<ol class="mt-2">
				<Action n={1} name="Get Contents of URL (change it)">
					<p>Replace the URL with <Copy value="{info.base}/categories" /></p>
					{@render more()}
					{@render method('GET')}
					<p>Keep the two headers.</p>
				</Action>
				<Action n={2} name="Get Dictionary Value">
					{@render add('Get Dictionary Value')}
					<p>Tap <strong>Key</strong> and type <code>categories</code>. Leave the rest.</p>
				</Action>
				<Action n={3} name="Choose from List">
					{@render add('Choose from List')}
					<p>It reads "Choose from <span class="text-accent-ink">Dictionary Value</span>". Leave that.</p>
					<p>Tap <strong>›</strong>, tap <strong>Prompt</strong>, and type <code>What was it?</code></p>
				</Action>
				<Action n={4} name="Ask for Input (the amount)">
					{@render add('Ask for Input')}
					<p>It reads "Ask for <span class="text-accent-ink">Text</span> with <span class="text-accent-ink">Prompt</span>". Tap <strong>Text</strong> and choose <strong>Number</strong>. Tap <strong>Prompt</strong> and type <code>How much?</code></p>
				</Action>
				<Action n={5} name="Ask for Input (the note)">
					{@render add('Ask for Input')}
					<p>Leave it as <strong>Text</strong>. Tap <strong>Prompt</strong> and type <code>Note (optional)</code>. When you run it you can leave this blank.</p>
				</Action>
				<Action n={6} name="Get Contents of URL (send it)">
					{@render add('Get Contents of URL')}
					{@render url('/tx')}
					{@render more()}
					{@render method('POST')}
					{@render headers()}
					<p>Tap <strong>Request Body</strong> and choose <strong>JSON</strong>. Then add three fields:</p>
					<div class="rounded-lg border border-line p-3">
						{@render field('Number', 'amount')}
						<p class="mt-1">
							Tap its value box, tap <strong>Select Variable</strong>, then tap step <strong>4</strong> (the "How much?" question). A blue
							<strong>Provided Input</strong> bubble appears.
						</p>
					</div>
					<div class="rounded-lg border border-line p-3">
						{@render field('Text', 'category')}
						<p class="mt-1">Tap its value box, then tap <strong>Chosen Item</strong> in the bar above the keyboard (or Select Variable → step 3).</p>
					</div>
					<div class="rounded-lg border border-line p-3">
						{@render field('Text', 'note')}
						<p class="mt-1">Tap its value box, tap <strong>Select Variable</strong>, then tap step <strong>5</strong> (the "Note" question).</p>
					</div>
					<p class="text-muted">
						Both questions give a bubble called "Provided Input". To tell them apart, tap a bubble → <strong>Rename</strong> → e.g. "Amount" and
						"Note".
					</p>
				</Action>
				{@render message(7)}
				{@render notify(8)}
			</ol>
			{@render looks([
				'Get contents of …/categories (GET, 2 headers)',
				'Get Value for categories in Contents of URL',
				'Choose from Dictionary Value — "What was it?"',
				'Ask for Number — "How much?"',
				'Ask for Text — "Note (optional)"',
				'Get contents of …/tx (POST, 2 headers, JSON: amount, category, note)',
				'Get Value for message in Contents of URL',
				'Show notification Dictionary Value'
			])}
			<p class="mt-3 text-sm">
				<strong>Test it:</strong> tap ▶, choose <strong>Other</strong>, enter <strong>0.01</strong>. You'll see "Logged $0.01 as Other…". Then run
				<strong>Undo Last</strong> to remove it.
			</p>
			<p class="mt-2 text-sm">
				<strong>Home Screen button:</strong> tap the name at the top → <strong>Add to Home Screen</strong> (on some iOS versions: the share button at
				the bottom → Add to Home Screen). "Hey Siri, log expense" works too.
			</p>
		</section>

		<!-- 5: Apple Pay -->
		<section class="card mt-4 p-5">
			{@render title(5, 'Log Apple Pay automatically', '6 min')}
			<p class="mt-2 text-sm text-ink-2">Every Apple Pay tap logs itself, and the app picks the budget line from the store's name.</p>
			<p class="mt-3 text-sm"><strong>Create the automation</strong> (automations can't be duplicated, so this one is typed from scratch):</p>
			<ol class="mt-2">
				<Action n={1} name="Start a new automation">
					<p>Shortcuts app → <strong>Automation</strong> tab at the bottom → <strong>+</strong> (top right, or "New Automation").</p>
					<p>Scroll the list and tap <strong>Apple Pay</strong> (older iOS: <em>Transaction</em> or <em>Wallet</em>).</p>
				</Action>
				<Action n={2} name="Choose the cards">
					<ul class="list-disc space-y-1 pl-5">
						<li><strong>Select</strong> your debit and credit cards, <strong>Apple Card</strong> (its spending never shows up in bank exports, so this is how the app sees it), and <strong>Apple Cash</strong>.</li>
						<li><strong>Unselect</strong> IDs and passes, such as a driver's license. They never make payments.</li>
						<li>Leave <strong>Categories</strong> and <strong>Merchants</strong> on everything. The app does the sorting.</li>
					</ul>
				</Action>
				<Action n={3} name="Make it run by itself">
					<p>Choose <strong>Run Immediately</strong> and turn <strong>Notify When Run</strong> off. Tap <strong>Next</strong>, then <strong>New Blank Automation</strong>.</p>
				</Action>
			</ol>
			<p class="mt-3 text-sm"><strong>Now add its actions</strong>, the same way as in a Shortcut:</p>
			<ol class="mt-2">
				<Action n={1} name="Get Contents of URL">
					{@render add('Get Contents of URL')}
					{@render url('/tx')}
					{@render more()}
					{@render method('POST')}
					{@render headers()}
					<p>Tap <strong>Request Body</strong> and choose <strong>JSON</strong>. Add four fields:</p>
					<div class="rounded-lg border border-line p-3">
						{@render field('Text', 'amount')}
						<p class="mt-1">
							Tap its value box and tap <strong>Shortcut Input</strong> above the keyboard. A blue bubble appears. <strong>Tap the bubble</strong> and
							choose <strong>Amount</strong>. The bubble now says "Amount".
						</p>
					</div>
					<div class="rounded-lg border border-line p-3">
						{@render field('Text', 'merchant')}
						<p class="mt-1">Same as above: insert <strong>Shortcut Input</strong>, tap the bubble, choose <strong>Merchant</strong>.</p>
					</div>
					<div class="rounded-lg border border-line p-3">
						{@render field('Text', 'category')}
						<p class="mt-1">
							Just <strong>type the word</strong> <code>auto</code>. It's not a variable. It tells Money Doctor to choose the budget line
							from the merchant (Kroger → Groceries, Shell → Gas). Stores it doesn't recognize go to "Other".
						</p>
					</div>
					<div class="rounded-lg border border-line p-3">
						{@render field('Text', 'card')}
						<p class="mt-1">
							Insert <strong>Shortcut Input</strong>, tap the bubble, choose <strong>Card or Pass</strong>. This tells Money Doctor which card
							you tapped, so the charge is counted in that card's payday payment.
						</p>
						<p class="mt-1 text-muted">Already built the automation? Open it, tap the Get Contents of URL action, and add just this field.</p>
					</div>
				</Action>
				{@render message(2)}
				{@render notify(3)}
			</ol>
			{@render looks([
				'Get contents of …/tx (POST, 2 headers, JSON: amount = Amount, merchant = Merchant, category = auto, card = Card or Pass)',
				'Get Value for message in Contents of URL',
				'Show notification Dictionary Value'
			])}
			<p class="mt-3 text-sm">Tap <strong>Done</strong>. <strong>Test it:</strong> pay with Apple Pay once. A notification names the budget line it chose.</p>
			<p class="mt-2 text-sm text-muted">
				It only fires on Apple Pay. Card swipes, and money sent with Cash App, Zelle, Venmo, PayPal or Apple Cash in Messages, don't trigger it.
				Use Log Expense for those. When the bank export arrives, it's matched to what you logged, so nothing counts twice.
			</p>
		</section>

		<!-- 6: Fix Last -->
		<section class="card mt-4 p-5">
			{@render title(6, 'Fix Last', '3 min')}
			<p class="mt-2 text-sm text-ink-2">
				When Apple Pay puts something in the wrong line (energy drinks at a gas station counted as Gas), run this and pick the right line. It moves the
				last thing you logged. You can also change any purchase on the website's Transactions page.
			</p>
			<p class="mt-3 text-sm">
				<strong>Create it by copying Log Expense</strong> (long-press → <strong>Duplicate</strong>), rename it <strong>Fix Last</strong>, then:
			</p>
			<ol class="mt-2">
				<Action n={1} name="Get Contents of URL (no change)"><p>Still gets the menu from <code>…/categories</code>.</p></Action>
				<Action n={2} name="Get Dictionary Value (no change)" />
				<Action n={3} name="Choose from List (change the prompt)">
					<p>Tap <strong>›</strong> and change <strong>Prompt</strong> to <code>Move the last entry to…</code></p>
				</Action>
				<Action n={4} name="Delete both Ask for Input actions">
					<p>Swipe left (or tap ✕) on the "How much?" and "Note" actions. They aren't needed here.</p>
				</Action>
				<Action n={5} name="Get Contents of URL (change it)">
					<p>Replace the URL with <Copy value="{info.base}/fix" /></p>
					<p>Tap <strong>›</strong>. In the JSON fields, delete <code>amount</code> and <code>note</code> (swipe left on each). Keep <code>category</code> = <strong>Chosen Item</strong>.</p>
				</Action>
				<Action n={6} name="Get Dictionary Value (no change)" />
				<Action n={7} name="Show Notification (no change)" />
			</ol>
			{@render looks([
				'Get contents of …/categories (GET, 2 headers)',
				'Get Value for categories in Contents of URL',
				'Choose from Dictionary Value — "Move the last entry to…"',
				'Get contents of …/fix (POST, 2 headers, JSON: category = Chosen Item)',
				'Get Value for message in Contents of URL',
				'Show notification Dictionary Value'
			])}
			<p class="mt-3 text-sm text-muted">
				Small gas-station purchases (under $15) already count as Dining &amp; snacks automatically; Fix Last is for everything else.
			</p>
		</section>

		<!-- 7: Share sheet -->
		<section class="card mt-4 p-5">
			{@render title(7, 'Send to Money Doctor (share sheet)', '5 min')}
			<p class="mt-2 text-sm text-ink-2">Sends pay statements, card statements, bank CSVs, and the household spreadsheet straight to the app.</p>
			<p class="mt-3 text-sm">
				<strong>Create it by copying Undo Last</strong> (long-press → <strong>Duplicate</strong>), rename it <strong>Send to Money Doctor</strong>.
			</p>
			<ol class="mt-2">
				<Action n="↑" name="Turn on the share sheet (this adds a line at the top)">
					<p>Tap the <strong>ⓘ</strong> button at the bottom of the editor (on some iOS versions: tap the name at the top → <strong>Details</strong>). Turn on <strong>Show in Share Sheet</strong>, then <strong>Done</strong>.</p>
					<p>
						A new first line appears: "Receive <span class="text-accent-ink">Any</span> input from Share Sheet". Tap <strong>Any</strong>, clear
						everything, and select only <strong>Files</strong> and <strong>PDFs</strong>.
					</p>
				</Action>
				<Action n={1} name="Get Contents of URL (change it)">
					<p>Replace the URL with <Copy value="{info.base}/documents" /></p>
					<p>Method stays <strong>POST</strong>, and keep the headers.</p>
					<p>Tap <strong>Request Body</strong> and choose <strong>Form</strong>. Tap <strong>Add new field</strong> → <strong>File</strong>. In <strong>Key</strong> type <code>files</code>. Tap its value box, then <strong>Shortcut Input</strong>.</p>
				</Action>
				<Action n={2} name="Get Dictionary Value (no change)" />
				<Action n={3} name="Show Notification (no change)" />
			</ol>
			{@render looks([
				'Receive Files and PDFs input from Share Sheet',
				'Get contents of …/documents (POST, 2 headers, Form: files = Shortcut Input)',
				'Get Value for message in Contents of URL',
				'Show notification Dictionary Value'
			])}
			<p class="mt-3 text-sm">
				<strong>Use it:</strong> open a PDF in Files, Safari or Mail → <strong>Share</strong> → <strong>Send to Money Doctor</strong>. Bank CSVs need
				the account in the file name (like <code>credit_card_1234_…</code>); the <a class="text-accent-ink" href="/upload">Upload page</a> asks
				for it instead.
			</p>
		</section>

		<!-- 7: Got Paid Back -->
		<section class="card mt-4 p-5">
			{@render title(8, 'Got Paid Back', '3 min')}
			<p class="mt-2 text-sm text-ink-2">
				When friends pay you back (Zelle, Venmo, Cash App) for something you covered, like pizza for everyone. It subtracts from that budget
				line, so it only counts your share.
			</p>
			<p class="mt-3 text-sm">
				<strong>Create it by copying Log Expense</strong> (long-press → <strong>Duplicate</strong>), rename it <strong>Got Paid Back</strong>, then
				change three things:
			</p>
			<ol class="mt-2">
				<Action n={3} name="Choose from List (change the prompt)">
					<p>Tap <strong>›</strong> and change <strong>Prompt</strong> to <code>What was it for?</code></p>
				</Action>
				<Action n={4} name="Ask for Input (change the prompt)">
					<p>Change <strong>Prompt</strong> to <code>How much did you get back?</code></p>
				</Action>
				<Action n={6} name="Get Contents of URL (add one field)">
					<p>Tap <strong>›</strong>, scroll to the JSON fields, tap <strong>Add new field</strong> and choose <strong>Boolean</strong>. In <strong>Key</strong> type <code>refund</code> and switch the value to <strong>True</strong>.</p>
				</Action>
			</ol>
			<p class="mt-3 text-sm text-muted">
				Pizza example: log the $300 with Log Expense (Dining), then each friend's $40 with Got Paid Back (Dining). Dining shows your real share.
				When the Zelle deposits arrive in the bank data, they match these entries; Venmo and Cash App cash-outs to the bank count as transfers, not income.
			</p>
		</section>

		<!-- 8: Email receipts -->
		<section class="card mt-4 p-5">
			{@render title(9, 'Email receipts: log Venmo, Zelle, Cash App, PayPal automatically', '15 min')}
			<p class="mt-2 text-sm text-ink-2">
				Each of these emails you a receipt for every payment. Money Doctor reads them from one Gmail label and logs the payment within a couple of
				minutes: who, how much, which way, and the memo. Do this part on a computer; Gmail's filter settings aren't in the phone app.
			</p>
			<ol class="mt-3">
				<Action n={1} name="Turn on 2-Step Verification (if it isn't already)">
					<p>Go to <Copy value="https://myaccount.google.com/security" /> → <strong>2-Step Verification</strong> → turn it on. Google requires it for app passwords.</p>
				</Action>
				<Action n={2} name="Create an app password">
					<p>Go to <Copy value="https://myaccount.google.com/apppasswords" />, type the name <code>Money Doctor</code>, and tap <strong>Create</strong>.</p>
					<p>Google shows a 16-letter password <strong>once</strong>. Keep it for step 6. It can only read mail through this app, and you can delete it any time.</p>
				</Action>
				<Action n={3} name="Create the label">
					<p>In Gmail on a computer: left sidebar → <strong>Labels +</strong> (Create new label) → name it exactly <code>Money Doctor</code> → <strong>Create</strong>.</p>
				</Action>
				<Action n={4} name="Create the filter">
					<p>Click the <strong>filter icon</strong> at the right end of Gmail's search bar. In <strong>From</strong>, paste:</p>
					<p><Copy value="venmo@venmo.com OR cash@square.com OR service@paypal.com OR ealerts.bankofamerica.com" /></p>
					<p>Click <strong>Create filter</strong>, tick <strong>Apply the label: Money Doctor</strong> and <strong>Also apply filter to matching conversations</strong>, then <strong>Create filter</strong>.</p>
					<p class="text-muted">If a receipt comes from a different address, open it, check who it's from, and add that address to the filter.</p>
				</Action>
				<Action n={5} name="Turn on Bank of America email alerts">
					<p>In the <strong>BoA app</strong>: Menu → <strong>Alerts</strong> (or Settings → Alerts). Choose <strong>email</strong> as the delivery for:</p>
					<ul class="list-disc space-y-1 pl-5">
						<li><strong>Zelle</strong>: money received and money sent.</li>
						<li>Each credit card and the debit card: <strong>purchase / transaction alerts</strong> with the lowest amount it allows (e.g. $0.01). This also catches card swipes that Apple Pay doesn't.</li>
					</ul>
				</Action>
				<Action n={6} name="Give the server the password">
					<p>On the server, open the app's <code>.env</code> file and add two lines:</p>
					<p><Copy value="MAIL_USER=you@gmail.com" /></p>
					<p><Copy value="MAIL_PASSWORD=the16letterpassword" /></p>
					<p>Then restart it: <Copy value="docker compose up -d" /> (in the folder with your <code>compose.yml</code>).</p>
				</Action>
				<Action n={7} name="Check it">
					<p>On the site: <a class="text-accent-ink" href="/settings">Settings</a> → <strong>Email receipts</strong> → <strong>Check now</strong>. Recent receipts show as "logged". Anything marked "needs a look" didn't match a known format; its pattern can be added in <code>app/mail.py</code>.</p>
				</Action>
			</ol>
			<p class="mt-3 text-sm text-muted">
				Once this is on, you don't need Got Paid Back or Log Expense for Venmo, Zelle, Cash App or PayPal. If you log one anyway, it's matched to the
				email so it isn't counted twice. New people land in "Other" or as a payback; set the right line on the Transactions page once and it's
				remembered for that person.
			</p>
		</section>

		<section class="card mt-4 p-5">
			<h2 class="label">Last: the morning email</h2>
			<p class="mt-2 text-sm">
				Find the 6:30 email. If it landed in <strong>Spam</strong> or <strong>Promotions</strong>, mark it <strong>Not spam</strong> or move it to
				Primary, and add <code>money@example.com</code> to your contacts so it keeps arriving.
			</p>
		</section>

		<section class="card mt-4 p-5">
			<h2 class="label">If something doesn't work</h2>
			<ul class="mt-2 list-disc space-y-1.5 pl-5 text-sm">
				<li><strong>"forbidden"</strong>: the two headers are missing or mistyped. Check the Key spelling and that the values have no extra spaces.</li>
				<li><strong>"not scoped for money…"</strong>: the service token needs <code>money.*</code> in the gateway's API scopes.</li>
				<li><strong>"No budget line called …"</strong>: the category text doesn't match a line; use the menu from /categories.</li>
				<li><strong>Nothing happens after Apple Pay</strong>: open the automation and check it's on, with Run Immediately selected.</li>
			</ul>
		</section>
	{/if}
</div>
