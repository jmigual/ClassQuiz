<!--
SPDX-FileCopyrightText: 2025 Marlon W (Mawoka)

SPDX-License-Identifier: MPL-2.0
-->

<script lang="ts">
	import type { EditorData } from '$lib/quiz_types';
	import { languageLabel } from '$lib/languages';
	import { getLocalization } from '$lib/i18n';

	const { t } = getLocalization();

	interface Props {
		data: EditorData;
		selected_question: number;
	}

	let { data = $bindable(), selected_question = $bindable() }: Props = $props();

	let active = $state('');

	let question = $derived(data.questions[selected_question]);
	// RANGE answers are a single object with no text, so there is nothing to translate there.
	let authored_answers = $derived(
		Array.isArray(question.answers) ? question.answers.map((a) => a.answer ?? '') : []
	);
	// Declared on the quiz now; legacy quizzes saved before that field existed fall back to
	// whatever languages the questions already have translations for.
	let quiz_languages = $derived(
		data.languages && data.languages.length > 0
			? data.languages
			: [...new Set(data.questions.flatMap((q) => Object.keys(q.translations ?? {})))].sort()
	);

	// The author may have removed a language from the quiz while it was the open tab.
	$effect(() => {
		if (active !== '' && !quiz_languages.includes(active)) {
			active = '';
		}
	});

	const strip_html = (text: string): string => text.replace(/<[^>]*>/g, '');

	// Keep every language's answers array index-parallel to the authored answers. This has to cover
	// all languages, not just the open tab: answers are added and removed by the editors above, and
	// a stale array would hand a player the translation of an answer that no longer exists.
	// ponytail: positional, so deleting a middle answer shifts the ones after it — same as the
	// authored right/color flags, which are positional too. Key the entries if that ever bites.
	const realign = () => {
		const translations = data.questions[selected_question].translations;
		if (!translations) {
			return;
		}
		const count = authored_answers.length;
		for (const entry of Object.values(translations)) {
			// Only write when something actually differs, so the effect can't retrigger itself.
			if (entry.answers.length !== count) {
				entry.answers.length = count;
			}
			for (let i = 0; i < count; i++) {
				entry.answers[i] ??= '';
			}
		}
	};

	$effect(() => {
		realign();
	});

	// A declared language has no per-question entry until it's opened. Create it on demand and
	// keep doing so as the author walks through the questions, or the open tab would come up
	// blank on the next question and have to be clicked again.
	$effect(() => {
		if (active === '' || !quiz_languages.includes(active)) {
			return;
		}
		const translations = (data.questions[selected_question].translations ??= {});
		translations[active] ??= { question: '', answers: [] };
		realign();
	});
</script>

{#if quiz_languages.length > 0}
	<div class="w-full px-10 pb-6">
		<div class="flex flex-wrap items-center gap-2 border-b border-gray-400 pb-2">
			<span class="text-sm opacity-70">{$t('editor.translations')}</span>
			<button
				type="button"
				class="rounded-t-lg px-3 py-1 text-sm transition"
				class:bg-gray-300={active === ''}
				class:dark:bg-gray-500={active === ''}
				onclick={() => (active = '')}
			>
				{data.original_language || $t('words.original_language')}
			</button>
			{#each quiz_languages as name}
				<button
					type="button"
					class="rounded-t-lg px-3 py-1 text-sm transition"
					class:bg-gray-300={active === name}
					class:dark:bg-gray-500={active === name}
					onclick={() => (active = name)}
				>
					{languageLabel(name)}
				</button>
			{/each}
		</div>

		{#if active !== '' && question.translations?.[active]}
			<div class="flex flex-col gap-2 pt-3">
				<input
					class="w-full rounded-lg border-2 border-gray-500 bg-transparent p-2 outline-hidden focus:shadow-2xl"
					bind:value={data.questions[selected_question].translations[active].question}
					placeholder={$t('editor.translate_placeholder', {
						text: strip_html(question.question)
					})}
				/>
				{#each authored_answers as authored, i}
					<input
						class="w-full rounded-lg border-2 border-gray-500 bg-transparent p-2 outline-hidden focus:shadow-2xl"
						bind:value={data.questions[selected_question].translations[active].answers[i]}
						placeholder={$t('editor.translate_placeholder', { text: authored })}
					/>
				{/each}
			</div>
		{/if}
	</div>
{/if}
