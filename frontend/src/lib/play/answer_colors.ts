// SPDX-FileCopyrightText: 2023 Marlon W (Mawoka)
//
// SPDX-License-Identifier: MPL-2.0

// Kahoot-style positional palette: red, blue, yellow, green.
export const default_colors = ['#E21B3C', '#1368CE', '#D89E00', '#26890C'];

// Old muddy defaults, kept only so quizzes saved before the recolor remap at render time.
const old_defaults: Record<string, string> = {
	'#D6EDC9': '#E21B3C',
	'#B07156': '#1368CE',
	'#7F7057': '#D89E00',
	'#4E6E58': '#26890C'
};

// answer.color is persisted game data: an old default remaps to the new color at the same
// position, a custom color a quiz author picked passes through unchanged, and no color falls
// back to the new default for that position.
// Known, accepted collision: a custom color that happens to equal one of the four old defaults
// is indistinguishable from one and gets remapped too — there's no way to tell them apart from
// the stored hex alone.
// ponytail: assumes index < 4 (every answer editor caps at 4 answers today); an out-of-range
// index returns undefined here and throws downstream in get_foreground_color. Add a 5th
// (purple) entry to default_colors if a >4-answer question type ever ships.
export const get_answer_color = (color: string | null | undefined, index: number): string => {
	if (!color) return default_colors[index];
	// The editor's <input type="color"> lowercases whatever it stores, so a saved default
	// comes back in either case depending on whether the author ever opened the picker.
	return old_defaults[color.toUpperCase()] ?? color;
};
