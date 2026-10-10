<!--
SPDX-FileCopyrightText: 2023 Marlon W (Mawoka)

SPDX-License-Identifier: MPL-2.0
-->
<script lang="ts">
	import { browser } from '$app/environment';
	import { LANGUAGES, type Language } from '$lib/languages';
	import { getLocalization } from '$lib/i18n';

	interface Props {
		languages?: Language[];
		compact?: boolean;
		// eslint-disable-next-line no-unused-vars
		onchange?: (code: string) => void;
	}

	let { languages = LANGUAGES, compact = false, onchange }: Props = $props();
	const { currentLanguage } = getLocalization();

	const set_language = (code: string): void => {
		if (browser) {
			localStorage.setItem('language', code);
			currentLanguage.set(code);
			onchange?.(code);
		}
	};
</script>

<div>
	<select
		value={$currentLanguage}
		onchange={(e) => {
			set_language(e.currentTarget.value);
		}}
		class={[
			'rounded-lg bg-gray-800 focus:ring-2 ring-blue-600 text-white',
			compact ? 'p-1 w-12 text-sm' : 'p-2'
		]}
		aria-label="Language-Selector"
	>
		{#each languages as lang}
			<option value={lang.code}>{lang.flag} {lang.name} </option>
		{/each}
	</select>
</div>
