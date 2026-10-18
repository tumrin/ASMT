// The Vite proxy (vite.config.ts) covers dev; the built adapter-node server has
// none, so this hook forwards /api/* to the backend with the same prefix strip.

import { API_URL } from '$app/env/private';
import type { Handle } from '@sveltejs/kit/hooks';

const API_PREFIX = '/api';

export const handle: Handle = async ({ event, resolve }) => {
	const { pathname } = event.url;
	if (pathname !== API_PREFIX && !pathname.startsWith(`${API_PREFIX}/`)) {
		return resolve(event);
	}

	try {
		const upstream = new URL(pathname.slice(API_PREFIX.length) + event.url.search, API_URL);
		return await fetch(new Request(upstream, event.request));
	} catch (err) {
		return Response.json(
			{ detail: `Could not reach the backend at ${API_URL}: ${String(err)}` },
			{ status: 502 }
		);
	}
};
