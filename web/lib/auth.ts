import { createHash, createHmac, scryptSync, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

const COOKIE_NAME = "daily_berlin_admin";
const SESSION_SECONDS = 60 * 60 * 8;

function secret(): string {
  const value = process.env.SESSION_SECRET;
  if (!value || value.length < 32) throw new Error("SESSION_SECRET must contain at least 32 characters");
  return value;
}

function signature(payload: string): string {
  return createHmac("sha256", secret()).update(payload).digest("base64url");
}

export function verifyAdminPassword(password: string): boolean {
  const configured = process.env.ADMIN_PASSWORD_HASH ?? "";
  const [salt, expectedHex] = configured.split(":", 2);
  if (!salt || !expectedHex || !/^[a-f0-9]+$/i.test(expectedHex)) return false;
  const actual = scryptSync(password, salt, expectedHex.length / 2);
  const expected = Buffer.from(expectedHex, "hex");
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

export function hasValidCronBearer(request: Request): boolean {
  const expected = process.env.CRON_SECRET?.trim();
  const match = /^Bearer\s+(.+)$/i.exec(request.headers.get("authorization") ?? "");
  const provided = match?.[1]?.trim() ?? "";
  const expectedDigest = createHash("sha256").update(expected ?? "").digest();
  const providedDigest = createHash("sha256").update(provided).digest();
  const matches = timingSafeEqual(providedDigest, expectedDigest);
  return Boolean(expected && provided && match && matches);
}

export async function createAdminSession(): Promise<void> {
  const expires = Math.floor(Date.now() / 1000) + SESSION_SECONDS;
  const payload = Buffer.from(JSON.stringify({ expires })).toString("base64url");
  const token = `${payload}.${signature(payload)}`;
  (await cookies()).set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: SESSION_SECONDS,
  });
}

export async function clearAdminSession(): Promise<void> {
  (await cookies()).delete(COOKIE_NAME);
}

export async function isAdmin(): Promise<boolean> {
  const token = (await cookies()).get(COOKIE_NAME)?.value;
  if (!token) return false;
  const [payload, provided] = token.split(".", 2);
  if (!payload || !provided) return false;
  const expected = signature(payload);
  const providedBuffer = Buffer.from(provided);
  const expectedBuffer = Buffer.from(expected);
  if (providedBuffer.length !== expectedBuffer.length || !timingSafeEqual(providedBuffer, expectedBuffer)) return false;
  try {
    const session = JSON.parse(Buffer.from(payload, "base64url").toString()) as { expires: number };
    return session.expires > Date.now() / 1000;
  } catch {
    return false;
  }
}
