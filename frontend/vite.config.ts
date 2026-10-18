import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv, type ProxyOptions } from 'vite';

export default defineConfig(({ mode }) => {
	// .env.[mode] is not loaded yet when this file runs, so load it explicitly.
	// Fall back to the same default as src/env.ts so dev works without an env file.
	const { API_URL } = loadEnv(mode, '.', '');
	const proxy: Record<string, ProxyOptions> = {
		'/api': {
			target: API_URL ?? 'http://127.0.0.1:8000',
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
				adapter: adapter()
			})
		],
		server: { proxy },
		preview: { proxy }
	};
});
