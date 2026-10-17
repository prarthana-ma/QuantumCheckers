/**
 * Connection states, kept in their own module so `Hud` and `GameScreen` agree
 * without either importing the other.
 */

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";