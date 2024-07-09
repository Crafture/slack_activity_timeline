import { Activity } from './activity.model';

export interface Day {
    date: Date,
	hour: string,
    activities: Activity[]
};
