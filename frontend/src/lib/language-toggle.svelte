<!--
SPDX-FileCopyrightText: 2023 Marlon W (Mawoka)

SPDX-License-Identifier: MPL-2.0
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { LANGUAGES, type Language } from '$lib/languages';

	interface Props {
		languages?: Language[];
	}

	let { languages = LANGUAGES }: Props = $props();
	const get_selected_language = (): string => {
		return localStorage.getItem('language');
	};
	let selected_language: string = $state();
	onMount(() => {
		selected_language = get_selected_language();
	});

	const set_language = (code: string): void => {
		if (browser) {
			localStorage.setItem('language', code);
			window.location.reload();
		}
	};
</script>

<div>
	<select
		bind:value={selected_language}
		onchange={() => {
			set_language(selected_language);
		}}
		class="p-2 rounded-lg bg-gray-800 focus:ring-2 ring-blue-600 text-white"
		aria-label="Language-Selector"
	>
		{#each languages as lang}
			<option value={lang.code}>{lang.flag} {lang.name} </option>
		{/each}
	</select>
</div>
