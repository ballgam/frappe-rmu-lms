/**
 * Languages offered when labelling a video's audio tracks.
 *
 * Codes are ISO 639-2/T, matching what ffprobe reads out of a container and
 * what a DASH manifest carries. This is a curated list rather than the full
 * ~500-entry standard: it is a dropdown an instructor scans, not a reference
 * table, and an unlisted language can still be typed in.
 */
export type AudioLanguage = { value: string; label: string }

export const AUDIO_LANGUAGES: AudioLanguage[] = [
	{ value: 'amh', label: 'Amharic' },
	{ value: 'ara', label: 'Arabic' },
	{ value: 'ben', label: 'Bengali' },
	{ value: 'mya', label: 'Burmese' },
	{ value: 'zho', label: 'Chinese' },
	{ value: 'nld', label: 'Dutch' },
	{ value: 'eng', label: 'English' },
	{ value: 'fas', label: 'Persian' },
	{ value: 'fra', label: 'French' },
	{ value: 'deu', label: 'German' },
	{ value: 'guj', label: 'Gujarati' },
	{ value: 'hau', label: 'Hausa' },
	{ value: 'hin', label: 'Hindi' },
	{ value: 'ind', label: 'Indonesian' },
	{ value: 'ita', label: 'Italian' },
	{ value: 'jpn', label: 'Japanese' },
	{ value: 'kan', label: 'Kannada' },
	{ value: 'kaz', label: 'Kazakh' },
	{ value: 'khm', label: 'Khmer' },
	{ value: 'kor', label: 'Korean' },
	{ value: 'kur', label: 'Kurdish' },
	{ value: 'mal', label: 'Malayalam' },
	{ value: 'mar', label: 'Marathi' },
	{ value: 'nep', label: 'Nepali' },
	{ value: 'orm', label: 'Oromo' },
	{ value: 'pus', label: 'Pashto' },
	{ value: 'pol', label: 'Polish' },
	{ value: 'por', label: 'Portuguese' },
	{ value: 'pan', label: 'Punjabi' },
	{ value: 'ron', label: 'Romanian' },
	{ value: 'rus', label: 'Russian' },
	{ value: 'srp', label: 'Serbian' },
	{ value: 'sin', label: 'Sinhala' },
	{ value: 'som', label: 'Somali' },
	{ value: 'spa', label: 'Spanish' },
	{ value: 'swa', label: 'Swahili' },
	{ value: 'tgl', label: 'Tagalog' },
	{ value: 'tam', label: 'Tamil' },
	{ value: 'tel', label: 'Telugu' },
	{ value: 'tha', label: 'Thai' },
	{ value: 'tir', label: 'Tigrinya' },
	{ value: 'tur', label: 'Turkish' },
	{ value: 'ukr', label: 'Ukrainian' },
	{ value: 'urd', label: 'Urdu' },
	{ value: 'uzb', label: 'Uzbek' },
	{ value: 'vie', label: 'Vietnamese' },
	{ value: 'yor', label: 'Yoruba' },
]
