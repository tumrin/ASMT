import adapter from '@sveltejs/adapter-auto';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv, type ProxyOptions } from 'vite';

export default defineConfig(({ mode }) => {
	// .env.[mode] is not loaded yet when this file runs, so load it explicitly.
	const { API_URL } = loadEnv(mode, '.', '');
	// Forward /api/* to the backend so the browser stays same-origin.
	const proxy: Record<string, ProxyOptions> = {
		'/api': {
			target: API_URL,
			rewrite: (path) => path.replace(/^\/api/, '')
		}
	};

	return {
		plugins: [
			sveltekit({
				compilerOptions: {
					// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
					runes: ({ filename }) =>
						filename.split(/[/\\]/).includes('node_modules') ? undefined : true
				},

				// adapter-auto only supports some environments, see https://svelte.dev/docs/kit/adapter-auto for a list.
				// If your environment is not supported, or you settled on a specific environment, switch out the adapter.
				// See https://svelte.dev/docs/kit/adapters for more information about adapters.
				adapter: adapter()
			})
		],
		server: { proxy },
		preview: { proxy }
	};
});
