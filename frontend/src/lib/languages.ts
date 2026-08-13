// SPDX-FileCopyrightText: 2025 Marlon W (Mawoka)
//
// SPDX-License-Identifier: MPL-2.0

export interface Language {
	code: string;
	name: string;
	flag: string;
}

// Shared by the UI language toggle, the player's join screen and the quiz editor's
// translation tabs. Keep in sync with the locale bundles in ./i18n/locales.
export const LANGUAGES: Language[] = [
	{ code: 'de', name: 'Deutsch', flag: '🇩🇪' },
	{ code: 'en', name: 'English', flag: '🇺🇲' },
	{ code: 'tr', name: 'Türkçe', flag: '🇹🇷' },
	{ code: 'fr', name: 'Français', flag: '🇫🇷' },
	{ code: 'id', name: 'Bahasa Indonesia', flag: '🇮🇩' },
	{ code: 'ca', name: 'Català', flag: '🇪🇸' },
	{ code: 'it', name: 'Italiano', flag: '🇮🇹' },
	{ code: 'es', name: 'Español', flag: '🇪🇸' },
	{ code: 'nb_NO', name: 'Norsk', flag: '🇳🇴' },
	{ code: 'zh_Hant', name: 'Chinese (traditional)', flag: '🇨🇳' },
	{ code: 'pl', name: 'Polski', flag: '🇵🇱' },
	{ code: 'pt', name: 'Português', flag: '🇵🇹' },
	{ code: 'uk', name: 'Українська', flag: '🇺🇦' },
	{ code: 'nl', name: 'Nederlands', flag: '🇳🇱' },
	{ code: 'hu', name: 'Magyar', flag: '🇭🇺' },
	{ code: 'vi', name: 'tiếng Việt', flag: '🇻🇳' },
	{ code: 'ta', name: 'Tamil', flag: '🇮🇳' },
	{ code: 'pt_BR', name: 'Brazil', flag: '🇧🇷' },
	{ code: 'ja', name: 'Japan', flag: '🇯🇵' }
];

export const languageLabel = (code: string): string => {
	const language = LANGUAGES.find((l) => l.code === code);
	return language ? `${language.flag} ${language.name}` : code;
};
