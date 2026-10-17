// Traffic light of an antibiogram cell (as served by the backend).
export type TrafficLight = 'green' | 'yellow' | 'red' | 'none';

// Traffic light -> cell background colour (palette in src/app.css). 'none' (not reportable) is grey.
export const TRAFFIC_LIGHT_COLORS: Record<TrafficLight, string> = {
	green: 'var(--color-traffic-green)',
	yellow: 'var(--color-traffic-yellow)',
	red: 'var(--color-traffic-red)',
	none: 'var(--color-traffic-none)'
};

export function trafficLightColor(light: TrafficLight): string {
	return TRAFFIC_LIGHT_COLORS[light];
}
