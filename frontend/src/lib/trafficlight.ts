// Traffic light of an antibiogram cell (as served by the backend).
export type TrafficLight = 'green' | 'yellow' | 'red' | 'none';

// Traffic light -> cell background colour. 'none' (not reportable) is grey.
export const TRAFFIC_LIGHT_COLORS: Record<TrafficLight, string> = {
	green: '#c8e6c9',
	yellow: '#fff59d',
	red: '#ef9a9a',
	none: '#e0e0e0'
};

export function trafficLightColor(light: TrafficLight): string {
	return TRAFFIC_LIGHT_COLORS[light];
}
