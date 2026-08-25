// SPDX-FileCopyrightText: 2023 Marlon W (Mawoka)
//
// SPDX-License-Identifier: MPL-2.0

import { browser } from '$app/environment';

// Struck-metal-plate gong, synthesized instead of shipped as a binary asset.
// Ratios are inharmonic (not 1,2,3,4...) because a real plate isn't a harmonic resonator.
const PARTIAL_RATIOS = [1, 1.5, 2.1, 2.7, 3.4, 4.2];
const BASE_FREQUENCY = 220;
// Per-partial gains (1/(i+1)) sum to well over 1 and clip the destination at full volume;
// normalize so the summed partials peak at unity.
const PARTIAL_GAIN_SUM = PARTIAL_RATIOS.reduce((sum, _, i) => sum + 1 / (i + 1), 0);

let ctx: AudioContext | undefined;

const get_ctx = (): AudioContext | undefined => {
	if (!browser) return undefined;
	if (!ctx) {
		ctx = new AudioContext();
	}
	return ctx;
};

export const resumeAudioContext = (): void => {
	const c = get_ctx();
	c?.resume().catch(() => {});
};

export const playGong = (volume: number): void => {
	if (volume <= 0) return;
	const c = get_ctx();
	if (!c) return;

	const now = c.currentTime;
	const master = c.createGain();
	master.gain.value = volume;
	master.connect(c.destination);

	PARTIAL_RATIOS.forEach((ratio, i) => {
		const detune = (Math.random() - 0.5) * 10; // a few cents of shimmer
		const decay = 1.8 + (i / (PARTIAL_RATIOS.length - 1)) * 1.7; // staggered 1.8-3.5s

		const osc = c.createOscillator();
		osc.type = 'sine';
		osc.frequency.value = BASE_FREQUENCY * ratio;
		osc.detune.value = detune;

		const gain = c.createGain();
		gain.gain.setValueAtTime(1 / (i + 1) / PARTIAL_GAIN_SUM, now);
		gain.gain.exponentialRampToValueAtTime(0.0001, now + decay);

		osc.connect(gain).connect(master);
		osc.start(now);
		osc.stop(now + decay);
	});

	// Bright mallet-strike transient: a short burst of filtered white noise.
	const noise_duration = 0.04;
	const noise_buffer = c.createBuffer(1, c.sampleRate * noise_duration, c.sampleRate);
	const data = noise_buffer.getChannelData(0);
	for (let i = 0; i < data.length; i++) {
		data[i] = Math.random() * 2 - 1;
	}

	const noise = c.createBufferSource();
	noise.buffer = noise_buffer;

	const highpass = c.createBiquadFilter();
	highpass.type = 'highpass';
	highpass.frequency.value = 2000;

	const noise_gain = c.createGain();
	noise_gain.gain.setValueAtTime(0.3, now);
	noise_gain.gain.exponentialRampToValueAtTime(0.0001, now + noise_duration);

	noise.connect(highpass).connect(noise_gain).connect(master);
	noise.start(now);
	noise.stop(now + noise_duration);
};
