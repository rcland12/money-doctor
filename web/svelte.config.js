import adapter from '@sveltejs/adapter-static';

/** A single-page app: the Python server serves index.html for every route. */
export default {
	kit: { adapter: adapter({ fallback: 'index.html' }) }
};
