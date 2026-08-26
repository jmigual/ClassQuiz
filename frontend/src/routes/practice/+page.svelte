<!--
SPDX-FileCopyrightText: 2023 Marlon W (Mawoka)

SPDX-License-Identifier: MPL-2.0
-->
<script lang="ts">
	import { page } from '$app/state';
	import type { QuizData } from '$lib/quiz_types';
	import Spinner from '$lib/Spinner.svelte';
	import TitleScreen from '$lib/practice/title_screen.svelte';
	import Question from '$lib/practice/question.svelte';
	import AudioPlayer from '$lib/play/audio_player.svelte';
	import { playGong, resumeAudioContext } from '$lib/play/gong.ts';
	import { QuizQuestionType } from '$lib/quiz_types';

	let quiz: QuizData = $state();
	let unique = $state({});

	let selected_question = $state(-1);
	// Lives here, not inside Question, because {#key unique} destroys/recreates Question on
	// every forward navigation, and mute/volume must survive that.
	let play_music = $state(false);
	let audio_muted = $state(false);
	let audio_volume = $state(100);

	const get_quiz = async () => {
		const res = await fetch(`/api/v1/quiz/get/public/${page.url.searchParams.get('quiz_id')}`);
		if (!res.ok) {
			throw res.status;
		}
		quiz = await res.json();
		return quiz;
	};
	const reload_q = () => {
		unique = {};
	};
	const go_to_question = (target: number) => {
		resumeAudioContext();
		// Recreate the Question instance on every nav (forward or back), not just forward: it
		// owns timer_res/time_up_fired, which must reset or the timer/gong can never fire again.
		reload_q();
		const target_question = quiz.questions[target];
		play_music = target !== -1 && target_question?.type !== QuizQuestionType.SLIDE;
		selected_question = target;
	};
	const on_time_up = () => {
		play_music = false;
		playGong(audio_muted ? 0 : audio_volume / 100);
	};
</script>

<svelte:window onpointerdown={resumeAudioContext} onkeydown={resumeAudioContext} />
<AudioPlayer bind:play={play_music} bind:muted={audio_muted} bind:volume={audio_volume} />
{#await get_quiz()}
	<Spinner />
{:then q}
	<div class="h-full overflow-hidden">
		{#if selected_question === -1}
			<TitleScreen bind:data={quiz} />
		{:else}
			{#key unique}
				<Question bind:question={quiz.questions[selected_question]} onTimeUp={on_time_up} />
			{/key}
		{/if}

		<div class="grid grid-cols-2 h-fit px-20 mt-6 absolute bottom-0 w-full">
			<button
				class="flex justify-start transition-all disabled:opacity-60"
				disabled={selected_question <= -1}
				onclick={() => go_to_question(selected_question - 1)}
			>
				<svg
					class="w-16 h-16"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
					xmlns="http://www.w3.org/2000/svg"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M15 19l-7-7 7-7"
					/>
				</svg>
			</button>
			<button
				class="flex justify-end transition-all disabled:opacity-60"
				disabled={selected_question >= quiz.questions.length - 1}
				onclick={() => go_to_question(selected_question + 1)}
			>
				<svg
					class="w-16 h-16"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
					xmlns="http://www.w3.org/2000/svg"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M9 5l7 7-7 7"
					/>
				</svg>
			</button>
		</div>
	</div>
{:catch e}
	{#if e === 404 || e === 400}
		<h1 class="text-center text-5xl">Quiz not found!</h1>
	{:else}
		<h1 class="text-center text-5xl">unknown error!</h1>
	{/if}
{/await}
