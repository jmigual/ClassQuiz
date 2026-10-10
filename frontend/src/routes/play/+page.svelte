<!--
SPDX-FileCopyrightText: 2023 Marlon W (Mawoka)

SPDX-License-Identifier: MPL-2.0
-->

<!--suppress ALL -->
<script lang="ts">
	import { socket } from '$lib/socket';
	import JoinGame from '$lib/play/join.svelte';
	import type { Answer, Question as QuestionType } from '$lib/quiz_types';
	import { QuizQuestionType } from '$lib/quiz_types';
	import ShowTitle from '$lib/play/title.svelte';
	import Question from '$lib/play/question.svelte';
	import { navbarVisible } from '$lib/stores.svelte.ts';
	import ShowEndScreen from '$lib/play/admin/final_results.svelte';
	import KahootResults from '$lib/play/results_kahoot.svelte';
	import { getLocalization } from '$lib/i18n';
	import { languageLabel } from '$lib/languages';
	import Cookies from 'js-cookie';
	const { t } = getLocalization();

	interface Props {
		// Exports
		data: any;
	}

	let { data }: Props = $props();
	let { game_pin } = $state(data);

	// Types
	interface GameMeta {
		started: boolean;
	}

	let game_mode = $state();
	let final_results: Array<null> | Array<Array<PlayerAnswer>> = $state([null]);

	interface PlayerAnswer {
		username: string;
		answer: string;
		right: string;
	}

	// Variables init
	let question_index = $state('');
	let unique = $state({});
	navbarVisible.visible = false;
	let answer_results: Array<Answer> = $state();
	let gameData: any = $state();
	let solution: QuestionType = $state();
	let username = $state('');
	let scores = $state({});
	let gameMeta: GameMeta = $state({
		started: false
	});

	let question: QuestionType = $state();
	let question_language: string | null = $state(null);

	let preventReload = true;

	// Functions
	function restart() {
		unique = {};
	}

	const confirmUnload = (event: Event) => {
		if (preventReload && gameData !== undefined) {
			event.preventDefault();
			// eslint-disable-next-line @typescript-eslint/ban-ts-comment
			// @ts-ignore
			event.returnValue = '';
		}
	};

	socket.on('time_sync', (data) => {
		socket.emit('echo_time_sync', data);
	});

	socket.on('connect', async () => {
		console.log('Connected!');
		const cookie_data = Cookies.get('joined_game');
		if (!cookie_data) {
			return;
		}
		const data = JSON.parse(cookie_data);
		socket.emit('rejoin_game', {
			old_sid: data.sid,
			username: data.username,
			game_pin: data.game_pin
		});
		const res = await fetch(`/api/v1/quiz/play/check_captcha/${game_pin}`);
		const json = await res.json();
		game_mode = json.game_mode;
	});

	// Socket-events
	socket.on('joined_game', (data) => {
		gameData = data;
		// eslint-disable-next-line no-undef
		plausible('Joined Game', { props: { game_id: gameData.game_id } });
		Cookies.set('joined_game', JSON.stringify({ sid: socket.id, username, game_pin }), {
			expires: 3600
		});
	});
	socket.on('rejoined_game', (data) => {
		gameData = data;
		if (data.started) {
			gameMeta.started = true;
		}
	});

	socket.on('game_not_found', () => {
		const cookie_data = Cookies.get('joined_game');
		if (cookie_data) {
			Cookies.remove('joined_game');
			window.location.reload();
			return;
		}
	});

	socket.on('set_question_number', (data) => {
		solution = undefined;
		restart();
		question = data.question;
		question_language = data.language;
		question_index = data.question_index;
		answer_results = undefined;
	});

	socket.on('start_game', () => {
		gameMeta.started = true;
	});

	socket.on('question_results', (data) => {
		restart();
		answer_results = data;
	});

	socket.on('username_already_exists', () => {
		window.alert('Username already exists!');
	});

	socket.on('kick', () => {
		window.alert('You got kicked');
		preventReload = false;
		game_pin = '';
		username = '';
		Cookies.remove('joined_game');
		window.location.reload();
	});
	socket.on('final_results', (data) => {
		final_results = data;
		Cookies.remove('joined_game');
	});

	socket.on('solutions', (data) => {
		solution = data;
	});

	// The server answers with the player's data in the new language, plus the question on screen
	// reworded (or nothing if it ignored the change or no question is up).
	const switch_language = (code: string) => {
		socket.emit('set_language', { language: code }, (data, q) => {
			if (data) gameData = data;
			// Swapped in place, without a new `unique`, so the timer and any pick carry on.
			if (q && q.question_index === question_index) {
				if (q.question.type === QuizQuestionType.ORDER) {
					// The player may have reordered; the server's order is the same in every language, so
					// each item's id is its position there.
					q.question.answers = question.answers.map((a) => ({
						...q.question.answers[a.id],
						id: a.id
					}));
				}
				question = q.question;
				question_language = q.language;
			}
		});
	};

	// The picker lives in a 40px strip at the top; every post-join screen keeps it free.
	let reserve_top = $derived(gameData?.languages?.length > 0);

	let bg_color = $derived(gameData ? gameData.background_color : undefined);

	// The rest
</script>

<svelte:window onbeforeunload={confirmUnload} />
<svelte:head>
	<title>ClassQuiz - Play</title>
</svelte:head>
<div
	class="min-h-dvh min-w-full"
	style="background: {bg_color ? bg_color : 'transparent'}"
	class:text-black={bg_color}
>
	{#if reserve_top}
		<div class="fixed top-1 right-2 z-50">
			<select
				value={gameData.language ?? ''}
				onchange={(e) => switch_language(e.currentTarget.value)}
				class="h-8 max-w-32 p-1 text-sm rounded-lg bg-gray-800 text-white focus:ring-2 ring-blue-600"
				aria-label={$t('words.language')}
			>
				<option value=""
					>{gameData.original_language || $t('words.original_language')}</option
				>
				{#each gameData.languages as code (code)}
					<option value={code}>{languageLabel(code)}</option>
				{/each}
			</select>
		</div>
	{/if}
	<div>
		{#if !gameMeta.started && gameData === undefined}
			<JoinGame bind:game_pin bind:game_mode bind:username />
		{:else if JSON.stringify(final_results) !== JSON.stringify([null])}
			<div class:pt-10={reserve_top}>
				<ShowEndScreen bind:data={scores} show_final_results={true} {username} />
			</div>
		{:else if gameData !== undefined && question_index === ''}
			<!-- Flex so ShowTitle's h-screen shrinks by the padding instead of overflowing it. -->
			<div class="flex flex-col h-screen" class:pt-10={reserve_top}>
				<ShowTitle
					title={gameData.title}
					description={gameData.description}
					cover_image={gameData.cover_image}
				/>
			</div>
		{:else if gameMeta.started && gameData !== undefined && question_index !== '' && answer_results === undefined}
			{#key unique}
				<div class="text-black dark:text-black">
					<Question
						bind:game_mode
						bind:question
						{question_index}
						{solution}
						{bg_color}
						language={question_language}
						{reserve_top}
					/>
				</div>
			{/key}
		{:else if gameMeta.started && answer_results !== undefined}
			<div class:pt-10={reserve_top}>
				{#if answer_results === null}
					<div class="w-full flex justify-center">
						<h1 class="text-3xl">{$t('admin_page.no_answers')}</h1>
					</div>
				{:else}
					<div>
						<h2 class="text-center text-3xl mb-8">
							{$t('words.result', { count: 2 })}
						</h2>
					</div>
					{#key unique}
						<KahootResults {username} question_results={answer_results} bind:scores />
					{/key}
				{/if}
			</div>
		{/if}
	</div>
</div>
