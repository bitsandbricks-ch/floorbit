/** How thick a link between switches is drawn, by planned speed in Gbit/s: the plan's network
 *  layer and the topology draw the same cable the same way (#1334). */
export const UPLINK_WIDTH: Record<number, number> = { 1: 1.5, 10: 2.5, 25: 3, 40: 4, 100: 5 }
