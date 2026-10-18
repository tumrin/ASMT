import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
	API_URL: {
		description: 'Backend base URL that /api/* requests are forwarded to.',
		schema: (value) => {
			if (value === undefined) return 'http://127.0.0.1:8000';
			try {
				new URL(value);
			} catch {
				throw new Error(`API_URL must be an absolute URL, got ${JSON.stringify(value)}`);
			}
			return value;
		}
	}
});
