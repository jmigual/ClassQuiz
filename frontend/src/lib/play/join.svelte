<!--
SPDX-FileCopyrightText: 2023 Marlon W (Mawoka)

SPDX-License-Identifier: MPL-2.0
-->

<script lang="ts">
	import { socket } from '$lib/socket';
	import { onDestroy, onMount } from 'svelte';
	import { browser } from '$app/environment';
	import * as Sentry from '@sentry/browser';
	import { getLocalization } from '$lib/i18n';
	import Cookies from 'js-cookie';
	import BrownButton from '$lib/components/buttons/brown.svelte';
	import { hcaptcha_site_key, recaptcha_key, sentry_dsn } from '$lib/config';
	import { languageLabel } from '$lib/languages';

	const { t } = getLocalization();

	interface Props {
		game_pin: string;
		game_mode: any;
		username: any;
	}

	let {
		game_pin = $bindable(),
		game_mode = $bindable(),
		username = $bindable()
	}: Props = $props();
	let custom_field = $state();
	let custom_field_value = $state();
	let captcha_enabled = $state();
	// Languages this quiz is translated into; empty means it's single-language and no picker shows.
	let quiz_languages: string[] = $state([]);
	// '' means play in the language the quiz was authored in.
	let selected_language = $state('');
	// Author-given name for that original language; falls back to the generic "Original" label.
	let original_language = $state('');

	let hcaptchaSitekey = hcaptcha_site_key;

	let hcaptcha = {
		execute: async (_a, _b) => ({ response: '' }), // eslint-disable-line @typescript-eslint/no-unused-vars
		// eslint-disable-next-line @typescript-eslint/no-empty-function
		render: (_a, _b) => {} // eslint-disable-line @typescript-eslint/no-unused-vars
	};
	let hcaptchaWidgetID;

	onMount(() => {
		if (browser) {
			prefetch_username();
			hcaptcha = window.hcaptcha;
			if (hcaptcha.render) {
				hcaptchaWidgetID = hcaptcha.render('hcaptcha', {
					sitekey: hcaptchaSitekey,
					size: 'invisible',
					theme: 'dark'
				});
			}
		}
	});

	onDestroy(() => {
		if (browser) {
			hcaptcha = {
				execute: async () => ({ response: '' }),
				// eslint-disable-next-line @typescript-eslint/no-empty-function
				render: () => {}
			};
		}
	});

	const prefetch_username = async () => {
		const res = await fetch('/api/v1/users/me');
		if (res.status !== 200) {
			return;
		}
		const json = await res.json();
		username = json.username;
	};

	const set_game_pin = async () => {
		let process_var;
		try {
			process_var = process;
		} catch {
			process_var = { env: { API_URL: undefined } };
		}

		const res = await fetch(
			`${process_var.env.API_URL ?? ''}/api/v1/quiz/play/check_captcha/${game_pin}`
		);
		const json = await res.json();
		game_mode = json.game_mode;
		if (res.status === 200) {
			captcha_enabled = json.enabled;
			custom_field = json.custom_field;
			quiz_languages = json.languages ?? [];
			// Reset first: this component survives a rejected pin, and a language picked for the
			// previous quiz must not be submitted for a different one that may not even offer it.
			selected_language = '';
			original_language = json.original_language ?? '';
			// Default to the language they're already reading the site in, if the quiz offers it.
			const ui_language = browser ? localStorage.getItem('language') : null;
			if (ui_language && quiz_languages.includes(ui_language)) {
				selected_language = ui_language;
			}
		}
		if (res.status === 404) {
			/*			alertModal.set({
                open: true,
                title: 'Game not found',
                body: 'The game pin you entered seems invalid.'
            });*/
			if (browser) {
				alert('Game not found');
			}
			game_pin = '';
			return;
		}
		if (res.status !== 200) {
			/*			alertModal.set({
                open: true,
                body: `Unknown error with response-code ${res.status}`,
                title: 'Unknown Error'
            });*/
			alert('Unknown error');
			return;
		}
	};

	$effect(() => {
		if (game_pin.length > 5) {
			set_game_pin();
		}
	});

	const setUsername = async (e: Event) => {
		e.preventDefault();
		if (username.length <= 3) {
			return;
		}
		let captcha_resp: string;
		if (Cookies.get('kicked')) {
			console.log("%cYou're Banned!", 'font-size:6rem');
			return;
		}

		if (captcha_enabled) {
			if (hcaptchaSitekey) {
				try {
					const { response } = await hcaptcha.execute(hcaptchaWidgetID, {
						async: true
					});
					captcha_resp = response;
					socket.emit('join_game', {
						username: username,
						game_pin: game_pin,
						captcha: captcha_resp,
						custom_field: custom_field ? custom_field_value : undefined,
						language: selected_language || undefined
					});
				} catch (e) {
					if (sentry_dsn !== null) {
						Sentry.captureException(e);
					}
					/*					alertModal.set({
                        open: true,
                        body: "The captcha failed, which is normal, but most of the time it's fixed by reloading!",
                        title: 'Captcha failed'
                    });*/
					alert('Captcha failed!');
					window.location.reload();
				}
			} else if (recaptcha_key) {
				// eslint-disable-next-line no-undef
				grecaptcha.ready(() => {
					// eslint-disable-next-line no-undef
					grecaptcha.execute(recaptcha_key, { action: 'submit' }).then(function (token) {
						socket.emit('join_game', {
							username: username,
							game_pin: game_pin,
							captcha: token,
							custom_field: custom_field ? custom_field_value : undefined,
							language: selected_language || undefined
						});
					});
				});
			}
		} else {
			socket.emit('join_game', {
				username: username,
				game_pin: game_pin,
				captcha: undefined,
				custom_field: custom_field ? custom_field_value : undefined,
				language: selected_language || undefined
			});
		}
	};
	socket.on('game_not_found', () => {
		game_pin = '';
		if (browser) {
			alert('Game not found');
		}
	});
	$effect(() => {
		const cleaned = game_pin.replace(/\D/g, '');
		if (game_pin.replace(/\D/g, '') === game_pin) {
			return;
		}
		game_pin = cleaned;
	});
</script>

<svelte:head>
	{#if captcha_enabled && hcaptchaSitekey}
		<script src="https://js.hcaptcha.com/1/api.js" async defer></script>
	{/if}
	{#if recaptcha_key && captcha_enabled}
		<script src="https://www.google.com/recaptcha/api.js?render={recaptcha_key}"></script>
	{/if}
</svelte:head>

{#if game_pin === '' || game_pin.length < 6}
	<div class="flex flex-col justify-center align-center w-screen h-screen">
		<form class="flex-col flex justify-center align-center mx-auto">
			<h1 class="text-lg text-center">{$t('words.game_pin')}</h1>
			<input
				class="border border-gray-400 self-center text-center text-black ring-0 outline-hidden p-2 rounded-lg focus:shadow-2xl transition-all"
				bind:value={game_pin}
				maxlength="6"
				inputmode="numeric"
			/>
			<!--				use:tippy={{content: "Please enter the game pin", sticky: true, placement: 'top'}}-->

			<br />
			<div class="mt-2">
				<BrownButton disabled={game_pin.length < 6}>{$t('words.submit')}</BrownButton>
			</div>
		</form>
	</div>
{:else}
	<div class="flex flex-col justify-center align-center w-screen h-screen">
		<form onsubmit={setUsername} class="flex-col flex justify-center align-center mx-auto">
			<h1 class="text-lg text-center">{$t('words.username')}</h1>
			<input
				class="border border-gray-400 self-center text-center text-black ring-0 outline-hidden p-2 rounded-lg focus:shadow-2xl transition-all"
				bind:value={username}
				maxlength="17"
			/>
			{#if custom_field}
				<h1 class="text-lg text-center">{custom_field}</h1>
				<input
					class="border border-gray-400 self-center text-center text-black ring-0 outline-hidden p-2 rounded-lg focus:shadow-2xl transition-all"
					bind:value={custom_field_value}
				/>
			{/if}
			{#if quiz_languages.length > 0}
				<h1 class="text-lg text-center mt-2">{$t('words.language')}</h1>
				<select
					class="border border-gray-400 self-center text-center bg-white text-black dark:bg-gray-700 dark:text-white ring-0 outline-hidden p-2 rounded-lg focus:shadow-2xl transition-all"
					bind:value={selected_language}
					aria-label={$t('words.language')}
				>
					<option value="" class="bg-white text-black dark:bg-gray-700 dark:text-white"
						>{original_language || $t('words.original_language')}</option
					>
					{#each quiz_languages as code}
						<option
							value={code}
							class="bg-white text-black dark:bg-gray-700 dark:text-white"
							>{languageLabel(code)}</option
						>
					{/each}
				</select>
			{/if}

			<div class="mt-2">
				<BrownButton disabled={username.length <= 3} onclick={setUsername}
					>{$t('words.submit')}</BrownButton
				>
			</div>
		</form>
	</div>
{/if}
<div
	id="hcaptcha"
	class="h-captcha"
	data-sitekey={hcaptchaSitekey}
	data-size="invisible"
	data-theme="dark"
></div>
