<!--
SPDX-FileCopyrightText: 2025 Marlon W (Mawoka)

SPDX-License-Identifier: MPL-2.0
-->

<script lang="ts">
	import type { EditorData } from '$lib/quiz_types';
	import { LANGUAGES, languageLabel } from '$lib/languages';
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
	// Union across the whole quiz: adding a language once makes its tab appear on every question,
	// so an author isn't re-adding it question by question.
	let quiz_languages = $derived(
		[...new Set(data.questions.flatMap((q) => Object.keys(q.translations ?? {})))].sort()
	);
	let unused_languages = $derived(LANGUAGES.filter((l) => !quiz_languages.includes(l.code)));

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

	const add_language = (code: string) => {
		if (!code) {
			return;
		}
		const translations = (data.questions[selected_question].translations ??= {});
		translations[code] ??= { question: '', answers: [] };
		realign();
		active = code;
	};

	const remove_language = (code: string) => {
		delete data.questions[selected_question].translations?.[code];
		if (active === code) {
			active = '';
		}
	};
</script>

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
			{$t('words.original_language')}
		</button>
		{#each quiz_languages as code}
			<span
				class="flex items-center gap-1 rounded-t-lg px-2 py-1 text-sm transition"
				class:bg-gray-300={active === code}
				class:dark:bg-gray-500={active === code}
			>
				<button type="button" onclick={() => (active = code)}>{languageLabel(code)}</button>
				<button
					type="button"
					class="opacity-50 hover:opacity-100"
					aria-label="Remove {code}"
					onclick={() => remove_language(code)}>&times;</button
				>
			</span>
		{/each}
		<select
			class="ml-auto rounded-lg border-2 border-gray-500 bg-transparent p-1 text-sm outline-hidden"
			value=""
			onchange={(e) => {
				add_language(e.currentTarget.value);
				e.currentTarget.value = '';
			}}
		>
			<option value="">{$t('editor.add_language')}</option>
			{#each unused_languages as language}
				<option value={language.code}>{language.flag} {language.name}</option>
			{/each}
		</select>
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
