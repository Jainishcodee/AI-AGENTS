/**
 * `server-only` throws on import outside a server bundle - that is the whole
 * point of it, and it is what stops the service-role key or a case solution
 * being pulled into a client component.
 *
 * Vitest resolves the client export condition and so trips the guard. Tests do
 * run on the server, so this stub stands in for it there and nowhere else.
 */
export {};
